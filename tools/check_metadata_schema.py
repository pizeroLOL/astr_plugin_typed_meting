from json import dumps
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl
from yaml import safe_load

PlatformName = Literal[
    "aiocqhttp",
    "qq_official",
    "qq_official_webhook",
    "telegram",
    "wecom",
    "wecom_ai_bot",
    "lark",
    "dingtalk",
    "discord",
    "slack",
    "kook",
    "vocechat",
    "weixin_official_account",
    "weixin_oc",
    "satori",
    "misskey",
    "line",
    "matrix",
    "mattermost",
]


class MetaData(BaseModel):
    name: str = Field(description="插件名称")
    desc: str = Field(description="插件长描述")
    """插件长描述"""
    repo: HttpUrl = Field(description="插件仓库")
    """插件仓库"""
    author: str = Field(description="插件作者")
    """插件作者"""
    version: str = Field(description="插件版本")
    """插件版本"""
    short_desc: str | None = Field(default=None, description="插件短描述，为空时使用 desc")
    display_name: str | None = Field(default=None, description="插件展示名，用于 webui")
    astrbot_version: str | None = Field(
        default=None, description="插件适配的 Astrbot 版本，使用类似 Python 标记的格式"
    )
    support_platforms: None | set[PlatformName] = Field(default=None, description="插件支持的平台")


if __name__ == "__main__":
    from pathlib import Path

    Path("tools/metadata.yaml.json-schema.json").write_text(
        dumps(MetaData.model_json_schema(mode="validation"), ensure_ascii=False),
        encoding="utf-8",
    )
    MetaData.model_validate(safe_load(Path("metadata.yaml").read_text(encoding="utf-8")))
