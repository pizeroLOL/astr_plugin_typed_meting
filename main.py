from typing import Literal
from uuid import UUID, uuid4

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Star
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.context import Context
from astrbot.core.utils.session_waiter import SessionController, session_waiter
from httpx import AsyncClient, HTTPError
from pydantic import ValidationError

from .cfg import Config
from .ty import PluginLogger, SongItem, Songs
from .utils import SOURCE_JUMP_MAPPER, build_card_info, build_card_msg, counter_waiter


class Plugin(Star):
    author = "pizeroLOL"
    name = "astr_plugin_typed_meting"
    cfg = Config()

    client: AsyncClient

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context, config)
        try:
            if config is not None:
                self.cfg = Config.model_validate(config)
                return
            logger.warning(f"[{self.name}] 未找到配置文件，已启用默认配置。")
        except ValidationError:
            logger.warning(
                f"[{self.name}] 初始化配置错误，已使用默认配置。",
                exc_info=True,
            )
            return

    async def initialize(self) -> None:
        self.client = AsyncClient()

    async def terminate(self) -> None:
        await self.client.aclose()

    def log(self, this: UUID) -> PluginLogger:
        def inner(
            mode: Literal["debug", "info", "warn", "critical"],
            msg: str,
            exc_info: bool = False,
        ) -> None:
            {
                "debug": logger.debug,
                "info": logger.info,
                "warn": logger.warning,
                "critical": logger.critical,
            }.get(mode, logger.info)(f"[{self.name}] <{this}> -> {msg}", exc_info=exc_info)

        return inner

    @filter.command("搜歌")
    async def search(self, event: AstrMessageEvent, keyword: str):
        log = self.log(uuid4())
        meting_cfg = self.cfg.meting
        url = meting_cfg.build_url(meting_cfg.url, keyword)
        log("debug", f"builded {url}")

        try:
            rsp = await self.client.get(url, follow_redirects=True)
            rsp.raise_for_status()
        except HTTPError as e:
            log("warn", f"`{e.request.url}` -> {e}", exc_info=True)
            yield event.plain_result("搜索响应错误")
            return

        songs: list[SongItem]
        log("debug", f"try parse `{rsp.text}`")

        try:
            songs = Songs.model_validate_json(rsp.text).root[: self.cfg.searching.results_limit]
        except ValidationError:
            log("warn", f"序列化错误 `{url}` -> {rsp.text!r}", exc_info=True)
            yield event.plain_result("搜索序列化错误")
            return

        if len(songs) == 0:
            yield event.plain_result("暂无歌曲")
            return

        info_msg = "输入 `点歌 <序号>` 来收听音乐\n输入 `取消` 以取消点歌"
        yield (
            event.plain_result(
                "\n".join(v.into_search_result(i + 1) for i, v in enumerate(songs)) + info_msg
            )
        )

        @session_waiter(timeout=self.cfg.searching.results_ttl_second, record_history_chains=False)
        @counter_waiter
        async def waiter(counter: int, controller: SessionController, event: AstrMessageEvent):
            msg = event.get_message_str().strip().strip("`")
            if msg == "退出":
                await event.send(event.plain_result("已退出"))
                controller.stop()
                return
            if not msg.startswith("点歌"):
                await event.send(event.plain_result("已退出"))
                controller.stop()
                return

            song: SongItem
            try:
                index = int(msg[2:]) - 1
                if index < 0:
                    raise ValueError(f"{index} -> 索引不可小于 0")
                song = songs[index]
            except (ValueError, IndexError):
                log("warn", f"用户输入错误 `{msg[2:]}`，列表为 {songs}", exc_info=True)
                if counter < 3:
                    await event.send(event.plain_result("输入错误\n" + info_msg))
                    controller.keep(self.cfg.searching.results_ttl_second, True)
                else:
                    await event.send(event.plain_result("输入错误次数过多，已退出"))
                    controller.stop()
                return
            if self.cfg.music_card.enable and (
                (it := meting_cfg.default_source) in SOURCE_JUMP_MAPPER
            ):
                card = await build_card_info(song, self.client, log, source=it)
                if card is None:
                    await event.send(event.plain_result("无法构造卡片"))
                    controller.stop()
                    return
                msg = await build_card_msg(
                    self.cfg.music_card,
                    card,
                    self.client,
                    log,
                )
                await event.send(MessageChain([msg]))
                return
            await event.send(event.plain_result("暂不支持卡片以外的返回方式"))
            controller.stop()
            return

        try:
            await waiter(event)
        except TimeoutError:
            log("info", "超时退出")
            yield event.plain_result("超时退出")
        except Exception:
            yield event.plain_result("未知错误")
        finally:
            event.stop_event()
