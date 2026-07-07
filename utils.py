from collections.abc import Awaitable, Callable
from typing import Literal

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.session_waiter import SessionController

from .ty import SongCardSupportSource

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


def counter_waiter(
    f: Callable[[int, SessionController, AstrMessageEvent], Awaitable[None]],
) -> Callable[[SessionController, AstrMessageEvent], Awaitable[None]]:
    counter = 0

    async def inner(ctrl: SessionController, event: AstrMessageEvent) -> None:
        nonlocal counter
        await f(counter, ctrl, event)
        counter += 1

    return inner
