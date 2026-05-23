from dataclasses import dataclass
from typing import Any, Literal, Protocol

from astrbot.api.message_components import Json
from pydantic import BaseModel, HttpUrl, RootModel, model_validator


def remap[T](d: dict[str, T], mapper: dict[str, str]) -> dict[str, T]:
    d.update(
        {
            target_key: value
            for source_key, target_key in mapper.items()
            if (value := d.get(source_key)) is not None
        }
    )
    return d


class SongItem(BaseModel):
    name: str
    artist: str
    album: str | None = None
    url: HttpUrl
    pic: HttpUrl

    @model_validator(mode="before")
    @classmethod
    def _map_node_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            remap(data, {"title": "name", "author": "artist"})
        return data

    def into_search_result(self, index: int) -> str:
        return f"{index}. {self.album + ' | ' if self.album is not None else ''}{self.name} - {self.artist}"


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
