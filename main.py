from asyncio import sleep
from string import Template
from typing import Literal
from uuid import UUID, uuid4

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.message_components import File
from astrbot.api.star import Star
from astrbot.core.config.default import VERSION
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.context import Context
from astrbot.core.utils.session_waiter import SessionController, session_waiter
from httpx import AsyncClient, HTTPError
from pydantic import BaseModel, Field, ValidationError

from .cfg import Config
from .ty import PluginLogger, SongItem, Songs
from .utils import (
    SOURCE_JUMP_MAPPER,
    build_card_info,
    build_card_msg,
    build_url,
    counter_waiter,
)

CLIENT_HEADER = {
    "Referer": "https://astrbot.app/",
    "User-Agent": f"AstrBot/{VERSION}",
    "UAK": "AstrBot/plugin_typed_meting",
}

SONG_TEMPLATE = """## $name

- 艺人：$artist
- 专辑图片：$pic
- 歌曲链接：$url
"""


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

    async def _send_song_result(
        self,
        event: AstrMessageEvent,
        song: SongItem,
        log: PluginLogger,
        controller: SessionController | None = None,
    ) -> None:
        """发送歌曲结果。优先构造音乐卡片，降级为直接发送文件。

        Args:
            event: 消息事件。
            song: 歌曲信息。
            log: 日志记录器。
            controller: 可选的 SessionController，传值时会在发送后自动 stop()。
        """
        if not self.cfg.music_card.enable:
            await event.send(MessageChain([File(name=f"{song.name}.mp3", url=str(song.url))]))
            if controller is not None:
                controller.stop()
            return

        default_source = self.cfg.meting.default_source
        if default_source not in SOURCE_JUMP_MAPPER:
            log(
                "warn",
                f"默认源不在卡片可制作的列表内 {default_source!r} not in {list(SOURCE_JUMP_MAPPER.keys())!r}",
            )
            await event.send(MessageChain([File(name=f"{song.name}.mp3", url=str(song.url))]))
            if controller is not None:
                controller.stop()
            return

        card = await build_card_info(song, self.client, log, source=default_source)
        if card is None:
            await event.send(event.plain_result("无法构造卡片"))
            await sleep(1)
            await event.send(MessageChain([File(name=f"{song.name}.mp3", url=str(song.url))]))
            if controller is not None:
                controller.stop()
            return

        msg = await build_card_msg(self.cfg.music_card, card, self.client, log)
        await event.send(MessageChain([msg]))
        if controller is not None:
            controller.stop()
        return

    async def _search_and_send_song(
        self,
        event: AstrMessageEvent,
        keyword: str,
        log: PluginLogger,
    ) -> str | None:
        """搜索歌曲并通过 event 发送音乐文件或卡片。

        处理搜索 Meting API、解析结果、构造并发送音乐卡片或文件。
        成功时歌曲已通过 event 发送，调用方只需处理返回的文本信息。

        Args:
            event: 消息事件，用于发送音乐文件/卡片。
            keyword: 搜索关键词。
            log: 日志记录器。

        Returns:
            成功时返回歌曲信息 Markdown 字符串。
            失败时返回 None（错误详情已写入日志）。
        """
        meting = self.cfg.meting
        url = build_url(meting, keyword)
        log("debug", f"builded {url}")

        try:
            rsp = await self.client.get(url, follow_redirects=True)
            rsp.raise_for_status()
        except HTTPError as e:
            log("warn", f"搜索响应错误 {url!r} -> {e}", exc_info=True)
            return None

        try:
            song = next(iter(Songs.model_validate_json(rsp.text).root), None)
        except ValidationError as e:
            log("warn", f"序列化错误 {url!r} -> {rsp.text!r}", exc_info=True)
            return None

        if song is None:
            log(
                "info",
                f"暂无歌曲 {event.session_id} / {event.get_sender_id} -> {event.message_str!r}",
            )
            return None

        song_info = Template(SONG_TEMPLATE).safe_substitute(song.model_dump(mode="json"))

        await self._send_song_result(event, song, log)
        return song_info

    @filter.llm_tool()
    async def order_song(self, event: AstrMessageEvent, keyword: str):
        """点歌
        用于给用户点歌，当返回歌曲信息的时候代表点歌已完成。

        Args:
            keyword(string): 关键词
        """
        log = self.log(uuid4())
        result = await self._search_and_send_song(event, keyword, log)
        return result or "搜索失败"

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
        result = await self._search_and_send_song(event, keyword, log)
        if result is None:
            yield event.plain_result("搜索失败")
            return

    @filter.command("搜歌")
    async def search(self, event: AstrMessageEvent):
        log = self.log(uuid4())
        keyword = event.message_str[3:].strip()
        if len(keyword) == 0:
            log(
                "info",
                f"搜歌缺少歌名 {event.session_id} / {event.get_sender_id} -> {event.message_str:!r} ",
            )
            yield event.plain_result("缺少歌名，请使用 `/搜歌 <歌名>` 的形式发起请求。")
            return
        meting_cfg = self.cfg.meting
        url = build_url(meting_cfg, keyword)
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

        info_msg = "\n输入 `点歌 <序号>` 来收听音乐\n输入 `取消` 以取消点歌"
        yield (
            event.plain_result(
                "\n".join(v.into_search_result(i + 1) for i, v in enumerate(songs)) + info_msg
            )
        )

        @session_waiter(timeout=self.cfg.searching.results_ttl_second, record_history_chains=False)
        @counter_waiter
        async def waiter(counter: int, controller: SessionController, event: AstrMessageEvent):
            await _handle_selection(self, counter, controller, event, songs, info_msg, log)

        try:
            await waiter(event)
        except TimeoutError:
            log("info", "超时退出")
            yield event.plain_result("超时退出")
        except Exception:
            yield event.plain_result("未知错误")
        finally:
            event.stop_event()


async def _handle_selection(
    plugin: Plugin,
    counter: int,
    controller: SessionController,
    event: AstrMessageEvent,
    songs: list[SongItem],
    info_msg: str,
    log: PluginLogger,
) -> None:
    """处理搜歌模式下用户选择序号后的点歌逻辑。"""
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
            controller.keep(plugin.cfg.searching.results_ttl_second, True)
        else:
            await event.send(event.plain_result("输入错误次数过多，已退出"))
            controller.stop()
        return

    await plugin._send_song_result(event, song, log, controller)
