from collections.abc import Awaitable, Callable
from dataclasses import asdict
from string import Template
from typing import Literal
from urllib.parse import quote

from astrbot.api.message_components import Json, Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.session_waiter import SessionController
from httpx import URL, AsyncClient, HTTPError
from pydantic import ValidationError

from .cfg import MusicCardConfig
from .ty import (
    CardInfo,
    CardSignResult,
    PluginLogger,
    SongCardSupportSource,
    SongItem,
)


def counter_waiter(
    f: Callable[[int, SessionController, AstrMessageEvent], Awaitable[None]],
) -> Callable[[SessionController, AstrMessageEvent], Awaitable[None]]:
    counter = 0

    async def inner(ctrl: SessionController, event: AstrMessageEvent) -> None:
        nonlocal counter
        await f(counter, ctrl, event)
        counter += 1

    return inner


async def get_redirct_url(client: AsyncClient, log: PluginLogger, url: str) -> str | None:
    try:
        log("debug", f"get_redirct_url {url}")
        rsp = await client.get(url, follow_redirects=False)
        return (
            str(location)
            if rsp.status_code in (301, 302, 303, 307, 308)
            and (location := rsp.headers.get("Location"))
            else None
        )
    except HTTPError as e:
        log("warn", f"{e.request.url} -> {e}", exc_info=True)


SOURCE_FORMAT_MAPPER: dict[Literal["netease", "tencent"] | str, Literal["163", "qq"]] = {
    "netease": "163",
    "tencent": "qq",
}

SOURCE_JUMP_MAPPER: dict[SongCardSupportSource, str] = {
    "netease": "https://music.163.com/#/song?id=$id",
    "tencent": "https://y.qq.com/n/ryqq/songDetail/$id",
    "bilibili": "https://www.bilibili.com/audio/$id",
    "kugou": "https://www.kugou.com/song/#$id",
    "kuwo": "https://kuwo.cn/play_detail/$id",
}


async def build_card_info(
    song: SongItem,
    client: AsyncClient,
    log: PluginLogger,
    source: SongCardSupportSource,
) -> CardInfo | None:
    id = URL(str(song.url)).params.get("id")
    if id is None:
        log("warn", f"url `{song.url}` 缺少id")
        return None
    raw_pic_url = (
        str(song.pic)
        if source != "netease"
        else (pic := str(song.pic)) + ("&" if "?" in pic else "?") + "picsize=320"
    )
    pic_url = await get_redirct_url(client, log, raw_pic_url)
    if pic_url is None:
        log("warn", f"缺少 `pic_url` {song.pic} -> {raw_pic_url} -> None")
        return None
    return CardInfo(
        song=song.name,
        singer=song.artist,
        cover=pic_url,
        jump=Template(SOURCE_JUMP_MAPPER[source]).substitute({"id": quote(id)}),
        format=SOURCE_FORMAT_MAPPER.get(source, source),
        url=str(song.url).replace("http://", "https://"),
    )


async def build_card_msg(
    cfg: MusicCardConfig, card_info: CardInfo, client: AsyncClient, log: PluginLogger
) -> Plain | Json:
    txt: str
    try:
        rsp = await client.get(cfg.sign_url, params=asdict(card_info), follow_redirects=True)
        rsp.raise_for_status()
        txt = rsp.text
    except HTTPError as e:
        log("warn", f"签名错误 {e.request.url} -> {e}", exc_info=True)
        return Plain("签名错误")

    try:
        return CardSignResult.model_validate_json(txt).into_json()
    except ValidationError:
        log("warn", f"签名序列化错误 `{txt}`", exc_info=True)
        return Plain("签名序列化错误")
