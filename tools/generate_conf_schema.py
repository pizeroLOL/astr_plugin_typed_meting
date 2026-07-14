#!/usr/bin/env python3
"""
Generate _conf_schema.json from cfg.py and validate it.

This script maps Pydantic field definitions to the AstrBot configuration schema
format used by _conf_schema.json, writes the file, then validates it against the
schema model definitions.

Usage:
    python tools/generate_conf_schema.py

The generated file is written to _conf_schema.json in the project root.
"""

from __future__ import annotations

import json
import sys
import typing
from pathlib import Path
from typing import Any, Literal, Self

# Ensure we can import cfg.py from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from annotated_types import Ge, Le
from pydantic import BaseModel, Field, RootModel, model_validator
from pydantic.fields import FieldInfo

import cfg

# ---------------------------------------------------------------------------
# Schema model definitions (used for validation)
# ---------------------------------------------------------------------------

type JsonDict = dict[str, Any]


class SliderInner(BaseModel):
    min: float
    max: float
    step: float

    @model_validator(mode="after")
    def _validate_min_max(self) -> Self:
        if self.min > self.max:
            raise ValueError(f"slider min ({self.min}) must be <= max ({self.max})")
        return self


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

    @model_validator(mode="after")
    def _validate_default_in_options(self) -> Self:
        """If both options and default are set, the default must be in the options list."""
        if (
            self.options is not None
            and self.default is not None
            and self.default not in self.options
        ):
            raise ValueError(f"default value {self.default!r} is not in options {self.options}")
        return self


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


class Int(FieldBase[Literal["int"], int]):
    slider: SliderInner | None = Field(description="暂无文档", default=None)

    @model_validator(mode="after")
    def _validate_default_within_slider(self) -> Self:
        """If both slider and default are set, the default must be within the slider range."""
        if (
            self.slider is not None
            and self.default is not None
            and (self.default < self.slider.min or self.default > self.slider.max)
        ):
            raise ValueError(
                f"default value {self.default!r} is outside slider range "
                f"[{self.slider.min}, {self.slider.max}]"
            )
        return self


class Float(FieldBase[Literal["float"], float]):
    slider: SliderInner | None = Field(description="暂无文档", default=None)

    @model_validator(mode="after")
    def _validate_default_within_slider(self) -> Self:
        """If both slider and default are set, the default must be within the slider range."""
        if (
            self.slider is not None
            and self.default is not None
            and (self.default < self.slider.min or self.default > self.slider.max)
        ):
            raise ValueError(
                f"default value {self.default!r} is outside slider range "
                f"[{self.slider.min}, {self.slider.max}]"
            )
        return self


class Bool(FieldBase[Literal["bool"], bool]):
    pass


class Object(FieldBase[Literal["object"], dict[str, object]]):
    items: None | dict[str, AllFieldTypes] = Field(
        description="可选。如果配置的类型是 object，需要添加 items 字段。items 的内容是这个配置项的子 Schema。理论上可以无限嵌套，但是不建议过多嵌套。",
        default=None,
    )

    @model_validator(mode="after")
    def _validate_items_required(self) -> Self:
        """Object type must have items defined to describe its sub-fields."""
        if self.items is None:
            raise ValueError("object type field must have 'items' defined")
        return self


class List(FieldBase[Literal["list"], list]):
    special: None | Literal["select_knowledgebase"] = Field(
        alias="_special",
        description="用于让用户快速选择在 WebUI 上已经配置好的知识库数据。",
        default=None,
    )


class Dict(FieldBase[Literal["dict"], dict[str, object]]):
    template_schema: None | dict[str, AllFieldTypes] = Field(
        description="可选填写 template schema，当设置之后，用户可以透过 WebUI 快速编辑。",
        default=None,
    )
    items: None | dict[str, AllFieldTypes] = Field(default=None)

    @model_validator(mode="after")
    def _validate_at_least_one_schema(self) -> Self:
        """Dict type should define at least one of items or template_schema."""
        if self.items is None and self.template_schema is None:
            raise ValueError(
                "dict type field should define at least one of 'items' or 'template_schema'"
            )
        return self


class TemplateList(FieldBase[Literal["template_list"], list[object]]):
    templates: None | dict[str, TemplateItem] = Field(
        description="可选填写 template schema，当设置之后，用户可以透过 WebUI 快速编辑。",
        default=None,
    )

    @model_validator(mode="after")
    def _validate_templates_required(self) -> Self:
        """TemplateList must have templates defined."""
        if self.templates is None:
            raise ValueError("template_list type field must have 'templates' defined")
        return self


class File(FieldBase[Literal["file"], list[str]]):
    file_types: set[str] | None = Field(description="允许上传的文件类型列表", default=None)


class TemplateItem(BaseModel):
    name: str | None = None
    hint: str | None = None
    display_item: str | None = None
    hide_hint_in_list: bool | None = None
    items: dict[str, AllFieldTypes]

    @model_validator(mode="after")
    def _validate_items_not_empty(self) -> Self:
        """TemplateItem must have at least one field defined in items."""
        if not self.items:
            raise ValueError("TemplateItem 'items' must not be empty")
        return self


type AllFieldTypes = String | Text | Int | Float | Bool | Object | List | Dict | TemplateList | File

ConfSchema = RootModel[dict[str, AllFieldTypes]]


# ---------------------------------------------------------------------------
# Schema generation helpers
# ---------------------------------------------------------------------------


def get_effective_type(annotation: Any) -> Any:
    """Unwrap Annotated to get the base type.

    e.g. Annotated[Literal["a"] | str, AfterValidator(...)] -> Literal["a"] | str
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return typing.get_args(annotation)[0]
    return annotation


def is_pure_literal(annotation: Any) -> bool:
    """Check if annotation is exactly Literal[...] (not Union[Literal, str] etc.)."""
    return typing.get_origin(annotation) is typing.Literal


def is_literal_str_union(annotation: Any) -> bool:
    """Check if annotation is Literal[...] | str (a Union of Literal and plain str)."""
    origin = typing.get_origin(annotation)
    if origin is None:
        return False
    args = typing.get_args(annotation)
    if len(args) < 2:
        return False
    has_literal = any(typing.get_origin(a) is typing.Literal for a in args)
    has_str = str in args
    return has_literal and has_str


def _apply_slider(schema: JsonDict, field_info: FieldInfo | None) -> None:
    """Attach slider constraints to an int/float schema entry."""
    if field_info is None:
        return
    ge = next((m.ge for m in field_info.metadata if isinstance(m, Ge)), None)
    le = next((m.le for m in field_info.metadata if isinstance(m, Le)), None)
    if ge is None and le is None:
        return
    slider: JsonDict = {"step": 1}
    if ge is not None:
        slider["min"] = ge
    if le is not None:
        slider["max"] = le
    schema["slider"] = slider


def _apply_common_metadata(schema: JsonDict, field_info: FieldInfo) -> None:
    """Attach title, description, and default to a non-object schema entry."""
    if field_info.title:
        schema["description"] = field_info.title
    if field_info.description:
        schema["hint"] = field_info.description
    if not field_info.is_required():
        default = field_info.default
        if not isinstance(default, BaseModel):
            schema["default"] = default


def _build_object_schema(field_info: FieldInfo, model_class: type[BaseModel]) -> JsonDict:
    """Build a schema entry for a nested Pydantic model."""
    schema: JsonDict = {"type": "object", "items": model_to_schema(model_class)}
    if field_info.title:
        schema["description"] = field_info.title
    if field_info.description:
        schema["hint"] = field_info.description
    return schema


def _build_scalar_or_literal_schema(effective: Any, field_info: FieldInfo | None) -> JsonDict:
    """Build a schema entry for built-in scalars and literal types."""
    # Pure literal -> string + options
    if is_pure_literal(effective):
        return {"type": "string", "options": list(typing.get_args(effective))}

    # Literal | str -> plain string (no options, accepts custom values)
    if is_literal_str_union(effective):
        return {"type": "string"}

    # Built-in types
    if isinstance(effective, type):
        if issubclass(effective, bool):
            return {"type": "bool"}
        if issubclass(effective, int):
            schema: JsonDict = {"type": "int"}
            _apply_slider(schema, field_info)
            return schema
        if issubclass(effective, float):
            schema: JsonDict = {"type": "float"}
            _apply_slider(schema, field_info)
            return schema

    # Fallback
    return {"type": "string"}


def _build_field_schema(_field_name: str, field_info: FieldInfo) -> JsonDict:
    """Convert a single Pydantic model field to an AstrBot schema entry."""
    effective = get_effective_type(field_info.annotation)

    # Nested model -> object (early return)
    if isinstance(effective, type) and issubclass(effective, BaseModel):
        return _build_object_schema(field_info, effective)

    schema = _build_scalar_or_literal_schema(effective, field_info)
    _apply_common_metadata(schema, field_info)
    return schema


def model_to_schema(model_class: type[BaseModel]) -> dict[str, JsonDict]:
    """Convert a Pydantic BaseModel to an AstrBot schema dict.

    Returns {field_name: field_schema, ...} suitable for an Object's ``items``.
    """
    result: dict[str, JsonDict] = {}
    for field_name, field_info in model_class.model_fields.items():
        result[field_name] = _build_field_schema(field_name, field_info)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    output_path = root_dir / "_conf_schema.json"

    # Generate
    schema = model_to_schema(cfg.Config)
    output_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"✓ Generated {output_path}")

    # Validate against schema model
    d = json.loads(output_path.read_text(encoding="utf-8"))
    ConfSchema.model_validate(d)
    print(f"✓ Validated {output_path} — all fields match the schema model")

    # Generate JSON Schema for reference
    schema_path = root_dir / "tools" / "_conf_schema.json-schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        json.dumps(ConfSchema.model_json_schema(mode="validation"), ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"✓ Generated JSON Schema reference at {schema_path}")


if __name__ == "__main__":
    main()
