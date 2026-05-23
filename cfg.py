from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    model_validator,
)
from pydantic_core import PydanticUseDefault

SOURCE_URL_MAPPER: dict[
    Literal[
        "https://musicapi.chuyel.top/meting/",
        "https://metingapi.nanorocky.top/",
    ]
    | str,
    Literal["node", "php", "custom"],
] = {
    "https://musicapi.chuyel.top/meting/": "node",
    "https://metingapi.nanorocky.top/": "php",
}


def patch_empty_str(value: str) -> str:
    if value.strip() == "":
        raise PydanticUseDefault()
    return value


class MetingConfig(BaseModel):
    url: Annotated[
        Literal["https://musicapi.chuyel.top/meting/", "https://metingapi.nanorocky.top/"] | str,
        AfterValidator(patch_empty_str),
    ] = Field(
        title="URL 地址",
        description="用于提供 Meting API 的 URL 地址，若选择了 custom 类型，请提供形如 `https://example.com/$$escape/${server}/${keyword}` 这样的字符串，样式参考 https://docs.python.org/3.11/library/string.html#template-strings 。注意，当 URL 为 `https://musicapi.chuyel.top/meting/` 时强制类型为 `node`，当 URL 为 `https://metingapi.nanorocky.top/` 时强制为 `php`。",
        default="https://musicapi.chuyel.top/meting/",
    )
    kind: Literal["node", "php", "custom"] = Field(
        title="类型",
        description="API 的类型，node 为 `https://github.com/metowolf/meting`，php 为 `https://github.com/nanorocky/meting-api`。",
        default="node",
    )
    default_source: Annotated[
        Literal["netease", "tencent", "kugou", "kuwo"] | str,
        AfterValidator(patch_empty_str),
    ] = Field(
        title="默认音源",
        description="具体见 API 文档，通常支持如下四个选项 `netease` 网易云音乐、`tencent` 腾讯音乐、`kugou` 酷狗音乐、`kuwo` 酷我音乐",
        default="netease",
    )

    @model_validator(mode="after")
    def validate_default_url(self) -> "MetingConfig":
        self.kind = SOURCE_URL_MAPPER.get(self.url, "custom")
        return self


class MusicCardConfig(BaseModel):
    enable: bool = Field(
        title="启用", description="是否使用个音乐卡片显示搜素结果。", default=False
    )
    sign_url: Annotated[
        Literal["https://oiapi.net/api/QQMusicJSONArk/"] | str,
        AfterValidator(patch_empty_str),
    ] = Field(
        title="签名地址",
        description="用于签名音乐卡片的 URL 地址，请保证以 `/` 结尾。",
        default="https://oiapi.net/api/QQMusicJSONArk/",
    )


class SearchConfig(BaseModel):
    results_ttl_second: int = Field(
        title="超时时间（秒）",
        description="搜索结果在制定时间后过期，范围为 30-300 秒。",
        ge=30,
        le=300,
        default=120,
    )
    results_limit: int = Field(
        title="结果上限",
        description="显示搜索结果时的条数上限，范围 5-30 条。",
        ge=5,
        le=30,
        default=10,
    )


class Config(BaseModel):
    meting: MetingConfig = Field(
        title="Meting",
        description="用于配置 Meting 的具体行为。",
        default=MetingConfig(),
    )
    music_card: MusicCardConfig = Field(
        title="音乐卡片",
        description="用于控制音乐卡片的具体行为。",
        default=MusicCardConfig(),
    )
    searching: SearchConfig = Field(
        title="搜索选项", description="用于控制搜索的具体行为。", default=SearchConfig()
    )
