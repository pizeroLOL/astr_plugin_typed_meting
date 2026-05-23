from typing import Any, Literal

from pydantic import BaseModel, Field, RootModel


class FieldBase[N, D](BaseModel):
    type: N = Field(
        description="此项必填。配置的类型。支持 string, text, int, float, bool, object, list, dict, template_list。当类型为 text 时，将会可视化为一个更大的可拖拽宽高的 textarea 组件，以适应大文本。"
    )
    description: str | None = Field(
        description="可选。配置的描述。建议一句话描述配置的行为。", default=None
    )
    hint: str | None = Field(
        description="可选。配置的提示信息，表现在上图中右边的问号按钮，当鼠标悬浮在问号按钮上时显示。",
        default=None,
    )
    obvious_hint: bool | None = Field(
        description="可选。配置的 hint 是否醒目显示。如上图的 token。", default=None
    )
    default: None | D = Field(
        description="可选。配置的默认值。如果用户没有配置，将使用默认值。int 是 0，float 是 0.0，bool 是 False，string 是 "
        "，object 是 {}，list 是 []。",
        default=None,
    )
    invisible: bool = Field(
        description="可选。配置是否隐藏。默认是 false。如果设置为 true，则不会在管理面板上显示。",
        default=False,
    )
    options: list[D] | None = Field(
        description='可选。一个列表，如 "options": ["chat", "agent", "workflow"]。提供下拉列表可选项。',
        default=None,
    )
    editor_mode: bool = Field(
        description="可选。是否启用代码编辑器模式。需要 AstrBot >= v3.5.10, 低于这个版本不会报错，但不会生效。默认是 false。",
        default=False,
    )
    editor_language: str | Literal["json"] = Field(
        description="可选。代码编辑器的代码语言，默认为 json。", default="json"
    )
    editor_theme: Literal["vs-light", "vs-dark"] = Field(
        description="可选。代码编辑器的主题，可选值有 vs-light（默认）， vs-dark。",
        default="vs-light",
    )


class String(FieldBase[Literal["string"], str]):
    special: (
        None
        | Literal[
            "select_provider",
            "select_provider_tts",
            "select_provider_stt",
            "select_persona",
        ]
    ) = Field(
        alias="_special",
        default=None,
        description="用于让用户快速选择在 WebUI 上已经配置好的模型提供商、tts、sst、人设数据。",
    )


class Text(FieldBase[Literal["text"], str]):
    pass


class SliderInner(BaseModel):
    min: float
    max: float
    step: float


class Int(FieldBase[Literal["int"], int]):
    slider: SliderInner | None = Field(description="暂无文档", default=None)


class Float(FieldBase[Literal["float"], float]):
    slider: SliderInner | None = Field(description="暂无文档", default=None)


class Bool(FieldBase[Literal["bool"], bool]):
    pass


class Object(
    FieldBase[
        Literal["object"],
        dict[str, Any],
    ]
):
    items: None | dict[str, Any] = Field(
        description="可选。如果配置的类型是 object，需要添加 items 字段。items 的内容是这个配置项的子 Schema。理论上可以无限嵌套，但是不建议过多嵌套。",
        default=None,
    )
    pass


class List(FieldBase[Literal["list"], list]):
    special: None | Literal["select_knowledgebase"] = Field(
        alias="_special",
        description="用于让用户快速选择在 WebUI 上已经配置好的知识库数据。",
        default=None,
    )
    pass


class Dict(FieldBase[Literal["dict"], dict[str, Any]]):
    template_schema: None | dict[str, Any] = Field(
        description="可选填写 template schema，当设置之后，用户可以透过 WebUI 快速编辑。",
        default=None,
    )
    items: None | dict = Field(default=None)


class TemplateList(FieldBase[Literal["template_list"], list[Any]]):
    templates: None | dict[str, Any] = Field(
        description="可选填写 template schema，当设置之后，用户可以透过 WebUI 快速编辑。",
        default=None,
    )
    pass


class File(FieldBase[Literal["file"], list[str]]):
    file_types: set[str] | None = Field(
        description="允许上传的文件类型列表", default=None
    )


type AllFieldTypes = (
    String | Text | Int | Float | Bool | Object | List | Dict | TemplateList | File
)

ConfSchema = RootModel[dict[str, AllFieldTypes]]

if __name__ == "__main__":
    from json import dumps, loads
    from pathlib import Path

    Path("tools/_conf_schema.json-schema.json").write_text(
        dumps(ConfSchema.model_json_schema(mode="validation"), ensure_ascii=False),
        encoding="utf-8",
    )
    d = loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    del d["$schema"]
    ConfSchema.model_validate(d)
    pass
