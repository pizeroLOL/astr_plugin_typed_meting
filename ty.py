from dataclasses import dataclass
from typing import Literal, Protocol

from astrbot.api.message_components import Json
from pydantic import BaseModel, HttpUrl, RootModel


class SongItem(BaseModel):
    name: str
    artist: str
    album: str | None
    url: HttpUrl
    pic: HttpUrl

    def into_search_result(self, index: int) -> str:
        return f"{index} {self.album + ' | ' if self.album is not None else ''}{self.name} - {self.artist}"


Songs = RootModel[list[SongItem]]

SongCardSupportSource = Literal["netease", "tencent", "bilibili", "kugou", "kuwo"]


class PluginLogger(Protocol):
    def __call__(
        self,
        mode: Literal["debug", "info", "warn", "critical"],
        msg: str,
        exc_info: bool = False,
    ) -> None: ...


@dataclass
class CardInfo:
    url: str
    song: str
    singer: str
    cover: str
    jump: str
    format: str


class CardSignDataConfig(BaseModel):
    token: str


class CardSignData(BaseModel):
    config: CardSignDataConfig


class CardSignResult(BaseModel):
    code: Literal[1]
    data: CardSignData

    def into_json(self) -> Json:
        return Json(data=self.data.model_dump(), config={"token": self.data.config.token})
