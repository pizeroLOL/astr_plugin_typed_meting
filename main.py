from typing import Literal
from uuid import UUID, uuid4

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Star
from astrbot.core.config.default import VERSION
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.context import Context
from astrbot.core.utils.session_waiter import SessionController, session_waiter
from httpx import AsyncClient
from pydantic import BaseModel, Field, ValidationError

from .cfg import Config
from .pipeline import (
    MetingAPIError,
    MetingError,
    MetingParseError,
    MetingPipeline,
    NoSongFoundError,
)
from .ty import PluginLogger, SongItem
from .utils import counter_waiter

CLIENT_HEADER = {
    "Referer": "https://astrbot.app/",
    "User-Agent": f"AstrBot/{VERSION}",
    "UAK": "AstrBot/plugin_typed_meting",
}


class TypedMetingInputs(BaseModel):
    keyword: str = Field(description="搜索的关键字。")
    limit: int | None = Field(description="用于控制最大返回的条数，为空则使用默认配置。")


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
            else:
                logger.warning(f"[{self.name}] 未找到配置文件，已启用默认配置。")
        except ValidationError:
            logger.warning(
                f"[{self.name}] 初始化配置错误，已使用默认配置。",
                exc_info=True,
            )

    async def initialize(self) -> None:
        self.client = AsyncClient(headers=CLIENT_HEADER)

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

    @filter.llm_tool()
    async def order_song(self, event: AstrMessageEvent, keyword: str):
        """点歌
        用于给用户点歌，当返回歌曲信息的时候代表点歌已完成。

        Args:
            keyword(string): 关键词
        """
        log = self.log(uuid4())
        pipeline = MetingPipeline(self.client, self.cfg, log=log)
        try:
            msg_chain, text = await pipeline.fetch_and_deliver_first(keyword)
        except NoSongFoundError:
            log(
                "info",
                f"暂无歌曲 {event.session_id} / {event.get_sender_id} -> {event.message_str!r}",
            )
            return "暂无歌曲"
        except MetingAPIError:
            return "搜索响应错误"
        except MetingParseError:
            return "搜索序列化错误"
        await event.send(msg_chain)
        return text

    @filter.command("点歌")
    async def order(self, event: AstrMessageEvent):
        log = self.log(uuid4())
        keyword = event.message_str[3:].strip()
        if len(keyword) == 0:
            log(
                "info",
                f"搜歌缺少歌名 {event.session_id} / {event.get_sender_id} -> {event.message_str!r} ",
            )
            yield event.plain_result("缺少歌名，请使用 `/点歌 <歌名>` 的形式发送请求。")
            return
        pipeline = MetingPipeline(self.client, self.cfg, log=log)
        try:
            msg_chain, _ = await pipeline.fetch_and_deliver_first(keyword)
        except NoSongFoundError:
            log(
                "info",
                f"暂无歌曲 {event.session_id} / {event.get_sender_id} -> {event.message_str!r}",
            )
            yield event.plain_result("暂无歌曲")
            return
        except MetingAPIError:
            yield event.plain_result("搜索响应错误")
            return
        except MetingParseError:
            yield event.plain_result("搜索序列化错误")
            return
        await event.send(msg_chain)

    @filter.command("搜歌")
    async def search(self, event: AstrMessageEvent):
        log = self.log(uuid4())
        keyword = event.message_str[3:].strip()
        if len(keyword) == 0:
            log(
                "info",
                f"搜歌缺少歌名 {event.session_id} / {event.get_sender_id} -> {event.message_str!r} ",
            )
            yield event.plain_result("缺少歌名，请使用 `/搜歌 <歌名>` 的形式发起请求。")
            return
        pipeline = MetingPipeline(self.client, self.cfg, log=log)
        try:
            songs = await pipeline.fetch_songs(keyword)
        except MetingAPIError:
            yield event.plain_result("搜索响应错误")
            return
        except MetingParseError:
            yield event.plain_result("搜索序列化错误")
            return

        songs = songs[: self.cfg.searching.results_limit]
        if len(songs) == 0:
            yield event.plain_result("暂无歌曲")
            return

        info_msg = "\n输入 `点歌 <序号>` 来收听音乐\n输入 `取消` 以取消点歌"
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
            try:
                msg_chain, _ = await pipeline.deliver_song(song)
            except MetingError:
                await event.send(event.plain_result("投递失败"))
                controller.stop()
                return
            await event.send(msg_chain)
            controller.stop()

        try:
            await waiter(event)
        except TimeoutError:
            log("info", "超时退出")
            yield event.plain_result("超时退出")
        except Exception:
            yield event.plain_result("未知错误")
        finally:
            event.stop_event()
