"""Tests for generate_conf_schema.py.

Usage:
    cd /home/pizero/Projects/astrbot/data/plugins/pylib-meting
    python -m unittest tools.test_generate_conf_schema -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Annotated, Any, Literal

# Ensure the project root is on sys.path for importing cfg & the module
_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))

from pydantic import BaseModel, Field, ValidationError
from pydantic.fields import FieldInfo

from tools import generate_conf_schema as gcs

# ============================================================================
#  Schema model validator tests
# ============================================================================


class TestSliderInnerValidator(unittest.TestCase):
    def test_valid_range(self):
        gcs.SliderInner(min=0, max=10, step=1)

    def test_invalid_min_gt_max(self):
        with self.assertRaises(ValueError):
            gcs.SliderInner(min=10, max=0, step=1)

    def test_equal_min_max(self):
        gcs.SliderInner(min=5, max=5, step=1)

    def test_negative_range(self):
        gcs.SliderInner(min=-10, max=-5, step=1)


class TestFieldBaseDefaultInOptions(unittest.TestCase):
    """Tests for FieldBase._validate_default_in_options."""

    def test_default_in_options_passes(self):
        gcs.String(type="string", default="b", options=["a", "b", "c"])

    def test_default_not_in_options_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gcs.String(type="string", default="z", options=["a", "b", "c"])
        self.assertIn("not in options", str(ctx.exception))

    def test_no_options_skips_validation(self):
        gcs.String(type="string", default="anything")

    def test_no_default_skips_validation(self):
        gcs.String(type="string", options=["a", "b"])

    def test_both_none_skips_validation(self):
        gcs.String(type="string")

    def test_int_default_in_options(self):
        gcs.Int(type="int", default=2, options=[1, 2, 3])

    def test_int_default_not_in_options(self):
        with self.assertRaises(ValueError):
            gcs.Int(type="int", default=99, options=[1, 2, 3])

    def test_float_default_in_options(self):
        gcs.Float(type="float", default=1.5, options=[1.0, 1.5, 2.0])

    def test_empty_options_list_with_default(self):
        with self.assertRaises(ValueError):
            gcs.String(type="string", default="x", options=[])


class TestIntSliderValidator(unittest.TestCase):
    """Tests for Int._validate_default_within_slider."""

    def test_default_within_range(self):
        gcs.Int(
            type="int",
            default=5,
            slider=gcs.SliderInner(min=0, max=10, step=1),
        )

    def test_default_at_min(self):
        gcs.Int(
            type="int",
            default=0,
            slider=gcs.SliderInner(min=0, max=10, step=1),
        )

    def test_default_at_max(self):
        gcs.Int(
            type="int",
            default=10,
            slider=gcs.SliderInner(min=0, max=10, step=1),
        )

    def test_default_below_min_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gcs.Int(
                type="int",
                default=-1,
                slider=gcs.SliderInner(min=0, max=10, step=1),
            )
        self.assertIn("outside slider range", str(ctx.exception))

    def test_default_above_max_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gcs.Int(
                type="int",
                default=20,
                slider=gcs.SliderInner(min=0, max=10, step=1),
            )
        self.assertIn("outside slider range", str(ctx.exception))

    def test_no_slider_skips_validation(self):
        gcs.Int(type="int", default=999)

    def test_no_default_skips_validation(self):
        gcs.Int(type="int", slider=gcs.SliderInner(min=0, max=10, step=1))


class TestFloatSliderValidator(unittest.TestCase):
    """Tests for Float._validate_default_within_slider."""

    def test_default_within_range(self):
        gcs.Float(
            type="float",
            default=5.5,
            slider=gcs.SliderInner(min=0.0, max=10.0, step=0.5),
        )

    def test_default_below_min_raises(self):
        with self.assertRaises(ValueError):
            gcs.Float(
                type="float",
                default=-1.0,
                slider=gcs.SliderInner(min=0.0, max=10.0, step=1.0),
            )

    def test_default_above_max_raises(self):
        with self.assertRaises(ValueError):
            gcs.Float(
                type="float",
                default=20.0,
                slider=gcs.SliderInner(min=0.0, max=10.0, step=1.0),
            )

    def test_no_slider_skips_validation(self):
        gcs.Float(type="float", default=999.0)


class TestObjectValidator(unittest.TestCase):
    """Tests for Object._validate_items_required."""

    def test_with_items_passes(self):
        gcs.Object(type="object", items={"key": gcs.String(type="string")})

    def test_without_items_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gcs.Object(type="object", items=None)
        self.assertIn("must have 'items' defined", str(ctx.exception))

    def test_empty_items(self):
        gcs.Object(type="object", items={})


class TestDictValidator(unittest.TestCase):
    """Tests for Dict._validate_at_least_one_schema."""

    def test_with_items_passes(self):
        gcs.Dict(type="dict", items={"key": gcs.String(type="string")})

    def test_with_template_schema_passes(self):
        gcs.Dict(
            type="dict",
            template_schema={"key": gcs.String(type="string")},
        )

    def test_with_both_passes(self):
        gcs.Dict(
            type="dict",
            items={"key": gcs.String(type="string")},
            template_schema={"tmpl": gcs.String(type="string")},
        )

    def test_without_schema_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gcs.Dict(type="dict", items=None, template_schema=None)
        self.assertIn("at least one of", str(ctx.exception))


class TestTemplateListValidator(unittest.TestCase):
    """Tests for TemplateList._validate_templates_required."""

    def test_with_templates_passes(self):
        gcs.TemplateList(
            type="template_list",
            templates={"tmpl": gcs.TemplateItem(items={"f": gcs.String(type="string")})},
        )

    def test_without_templates_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gcs.TemplateList(type="template_list", templates=None)
        self.assertIn("must have 'templates' defined", str(ctx.exception))


class TestTemplateItemValidator(unittest.TestCase):
    """Tests for TemplateItem._validate_items_not_empty."""

    def test_non_empty_items_passes(self):
        gcs.TemplateItem(items={"field": gcs.String(type="string")})

    def test_empty_items_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gcs.TemplateItem(items={})
        self.assertIn("must not be empty", str(ctx.exception))


# ============================================================================
#  Helper function tests
# ============================================================================


class TestGetEffectiveType(unittest.TestCase):
    def test_unwraps_annotated(self):
        ann = Annotated[str, "meta"]
        self.assertIs(gcs.get_effective_type(ann), str)

    def test_unwraps_nested_annotated(self):
        ann = Annotated[Annotated[int, "x"], "y"]
        self.assertIs(gcs.get_effective_type(ann), int)

    def test_plain_type_passthrough(self):
        self.assertIs(gcs.get_effective_type(float), float)

    def test_literal_passthrough(self):
        lit = Literal["a", "b"]
        self.assertIs(gcs.get_effective_type(lit), lit)

    def test_union_passthrough(self):
        ann = Literal["a"] | str
        self.assertIs(gcs.get_effective_type(ann), ann)

    def test_none_annotation(self):
        self.assertIsNone(gcs.get_effective_type(None))


class TestIsPureLiteral(unittest.TestCase):
    def test_pure_literal(self):
        self.assertTrue(gcs.is_pure_literal(Literal["a", "b"]))

    def test_single_value_literal(self):
        self.assertTrue(gcs.is_pure_literal(Literal["a"]))

    def test_literal_str_union_is_not_pure(self):
        self.assertFalse(gcs.is_pure_literal(Literal["a"] | str))

    def test_plain_type(self):
        self.assertFalse(gcs.is_pure_literal(str))

    def test_annotated_literal(self):
        """Annotated[Literal[...], ...] should be unwrapped first."""
        ann = Annotated[Literal["a", "b"], "meta"]
        # Without unwrapping, the origin is Annotated, not Literal
        self.assertFalse(gcs.is_pure_literal(ann))
        # After unwrapping, it is pure Literal
        self.assertTrue(gcs.is_pure_literal(gcs.get_effective_type(ann)))


class TestIsLiteralStrUnion(unittest.TestCase):
    def test_literal_str_union(self):
        self.assertTrue(gcs.is_literal_str_union(Literal["a"] | str))

    def test_multiple_literals_with_str(self):
        self.assertTrue(gcs.is_literal_str_union(Literal["a", "b"] | str))

    def test_reversed_order(self):
        """str | Literal['a'] should also be detected."""
        self.assertTrue(gcs.is_literal_str_union(str | Literal["a"]))

    def test_pure_literal(self):
        self.assertFalse(gcs.is_literal_str_union(Literal["a", "b"]))

    def test_plain_str(self):
        self.assertFalse(gcs.is_literal_str_union(str))

    def test_plain_int(self):
        self.assertFalse(gcs.is_literal_str_union(int))

    def test_literal_int_union_is_false(self):
        """Only str unions are relevant; Literal[int] | int should be False."""
        self.assertFalse(gcs.is_literal_str_union(Literal[1, 2] | int))

    def test_annotated_literal_str_union(self):
        """Annotated wrapping should be unwrapped before check."""
        ann = Annotated[Literal["a"] | str, "meta"]
        self.assertFalse(gcs.is_literal_str_union(ann))
        self.assertTrue(gcs.is_literal_str_union(gcs.get_effective_type(ann)))


# ============================================================================
#  Schema generation helper tests
# ============================================================================


class TestApplySlider(unittest.TestCase):
    @staticmethod
    def _field_info(**kwargs) -> FieldInfo:
        class _M(BaseModel):
            x: int = Field(**kwargs)

        return _M.model_fields["x"]

    def test_both_ge_and_le(self):
        schema: dict[str, Any] = {}
        gcs._apply_slider(schema, self._field_info(ge=10, le=20))
        self.assertEqual(schema, {"slider": {"step": 1, "min": 10, "max": 20}})

    def test_ge_only(self):
        schema: dict[str, Any] = {}
        gcs._apply_slider(schema, self._field_info(ge=5))
        self.assertEqual(schema, {"slider": {"step": 1, "min": 5}})

    def test_le_only(self):
        schema: dict[str, Any] = {}
        gcs._apply_slider(schema, self._field_info(le=100))
        self.assertEqual(schema, {"slider": {"step": 1, "max": 100}})

    def test_neither_ge_nor_le(self):
        schema: dict[str, Any] = {}
        gcs._apply_slider(schema, self._field_info())
        self.assertEqual(schema, {})

    @staticmethod
    def _float_field_info(**kwargs) -> FieldInfo:
        class _M(BaseModel):
            x: float = Field(**kwargs)

        return _M.model_fields["x"]

    def test_float_ge_le(self):
        schema: dict[str, Any] = {}
        gcs._apply_slider(schema, self._float_field_info(ge=0.5, le=10.5))
        self.assertEqual(schema, {"slider": {"step": 1, "min": 0.5, "max": 10.5}})


class TestApplyCommonMetadata(unittest.TestCase):
    @staticmethod
    def _field_info(**kwargs) -> FieldInfo:
        class _M(BaseModel):
            x: int = Field(**kwargs)

        return _M.model_fields["x"]

    def test_title_and_description(self):
        schema: dict[str, Any] = {}
        gcs._apply_common_metadata(schema, self._field_info(title="T", description="D"))
        self.assertEqual(schema, {"description": "T", "hint": "D"})

    def test_title_only(self):
        schema: dict[str, Any] = {}
        gcs._apply_common_metadata(schema, self._field_info(title="T"))
        self.assertEqual(schema, {"description": "T"})

    def test_description_only(self):
        schema: dict[str, Any] = {}
        gcs._apply_common_metadata(schema, self._field_info(description="D"))
        self.assertEqual(schema, {"hint": "D"})

    def test_with_default(self):
        schema: dict[str, Any] = {}
        gcs._apply_common_metadata(schema, self._field_info(default=42))
        self.assertEqual(schema, {"default": 42})

    def test_required_field_no_default(self):
        """Required fields (no default) should not get a default key."""
        schema: dict[str, Any] = {}
        # Field() without default makes it required
        gcs._apply_common_metadata(schema, self._field_info())
        self.assertEqual(schema, {})

    def test_optional_with_none_default(self):
        """Field(default=None) sets default to None, which should be written."""
        schema: dict[str, Any] = {}
        gcs._apply_common_metadata(schema, self._field_info(default=None))
        self.assertEqual(schema, {"default": None})

    def test_omits_default_when_it_is_a_basemodel(self):
        """Default values that are BaseModel instances should be omitted."""

        class MyModel(BaseModel):
            v: int = 0

        schema: dict[str, Any] = {}
        gcs._apply_common_metadata(schema, self._field_info(default=MyModel()))
        self.assertEqual(schema, {})

    def test_combined(self):
        schema: dict[str, Any] = {}
        gcs._apply_common_metadata(schema, self._field_info(title="T", description="D", default=42))
        self.assertEqual(schema, {"description": "T", "hint": "D", "default": 42})


class TestBuildObjectSchema(unittest.TestCase):
    def test_basic(self):
        class Inner(BaseModel):
            name: str = Field(title="Name", description="The name")

        class Outer(BaseModel):
            inner: Inner = Field(title="InnerObj", description="Inner description")

        field_info = Outer.model_fields["inner"]
        schema = gcs._build_object_schema(field_info, Inner)
        self.assertEqual(
            schema,
            {
                "type": "object",
                "items": {
                    "name": {
                        "type": "string",
                        "description": "Name",
                        "hint": "The name",
                    }
                },
                "description": "InnerObj",
                "hint": "Inner description",
            },
        )

    def test_no_title_no_description(self):
        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            inner: Inner

        field_info = Outer.model_fields["inner"]
        schema = gcs._build_object_schema(field_info, Inner)
        self.assertEqual(
            schema,
            {"type": "object", "items": {"x": {"type": "int"}}},
        )


class TestBuildScalarOrLiteralSchema(unittest.TestCase):
    @staticmethod
    def _field_info(**kwargs) -> FieldInfo:
        class _M(BaseModel):
            x: int = Field(**kwargs)

        return _M.model_fields["x"]

    def test_pure_literal(self):
        effective = Literal["a", "b", "c"]
        schema = gcs._build_scalar_or_literal_schema(effective, None)
        self.assertEqual(schema, {"type": "string", "options": ["a", "b", "c"]})

    def test_single_pure_literal(self):
        effective = Literal["only"]
        schema = gcs._build_scalar_or_literal_schema(effective, None)
        self.assertEqual(schema, {"type": "string", "options": ["only"]})

    def test_literal_str_union(self):
        effective = Literal["a", "b"] | str
        schema = gcs._build_scalar_or_literal_schema(effective, None)
        self.assertEqual(schema, {"type": "string"})

    def test_bool(self):
        schema = gcs._build_scalar_or_literal_schema(bool, None)
        self.assertEqual(schema, {"type": "bool"})

    def test_int(self):
        fi = self._field_info()
        schema = gcs._build_scalar_or_literal_schema(int, fi)
        self.assertEqual(schema, {"type": "int"})

    def test_int_with_slider(self):
        field_info = self._field_info(ge=1, le=10)
        effective = gcs.get_effective_type(field_info.annotation)
        schema = gcs._build_scalar_or_literal_schema(effective, field_info)
        self.assertEqual(
            schema,
            {"type": "int", "slider": {"step": 1, "min": 1, "max": 10}},
        )

    @staticmethod
    def _float_field_info(**kwargs) -> FieldInfo:
        class _FM(BaseModel):
            x: float = Field(**kwargs)

        return _FM.model_fields["x"]

    def test_float(self):
        fi = self._float_field_info()
        schema = gcs._build_scalar_or_literal_schema(float, fi)
        self.assertEqual(schema, {"type": "float"})

    def test_float_with_slider(self):
        field_info = self._float_field_info(ge=0.5, le=10.5)
        effective = gcs.get_effective_type(field_info.annotation)
        schema = gcs._build_scalar_or_literal_schema(effective, field_info)
        self.assertEqual(
            schema,
            {"type": "float", "slider": {"step": 1, "min": 0.5, "max": 10.5}},
        )

    def test_plain_str_fallsback(self):
        """Plain str without Literal falls back to type string."""
        schema = gcs._build_scalar_or_literal_schema(str, self._field_info())
        self.assertEqual(schema, {"type": "string"})

    def test_any_fallsback(self):
        """Any type falls back to type string."""
        schema = gcs._build_scalar_or_literal_schema(Any, self._field_info())
        self.assertEqual(schema, {"type": "string"})


class TestBuildFieldSchema(unittest.TestCase):
    def test_nested_model(self):
        class Inner(BaseModel):
            val: int = Field(title="V", default=0)

        class Outer(BaseModel):
            inner: Inner = Field(title="InnerField")

        field_info = Outer.model_fields["inner"]
        schema = gcs._build_field_schema("inner", field_info)
        self.assertEqual(
            schema,
            {
                "type": "object",
                "items": {"val": {"type": "int", "description": "V", "default": 0}},
                "description": "InnerField",
            },
        )

    def test_string_field(self):
        class M(BaseModel):
            name: str = Field(title="Name", description="The name", default="")

        schema = gcs._build_field_schema("name", M.model_fields["name"])
        self.assertEqual(
            schema,
            {"type": "string", "description": "Name", "hint": "The name", "default": ""},
        )

    def test_bool_field(self):
        class M(BaseModel):
            flag: bool = Field(title="Flag", default=False)

        schema = gcs._build_field_schema("flag", M.model_fields["flag"])
        self.assertEqual(schema, {"type": "bool", "description": "Flag", "default": False})

    def test_int_field(self):
        class M(BaseModel):
            count: int = Field(title="Count", default=10)

        schema = gcs._build_field_schema("count", M.model_fields["count"])
        self.assertEqual(schema, {"type": "int", "description": "Count", "default": 10})

    def test_float_field(self):
        class M(BaseModel):
            ratio: float = Field(title="Ratio", default=1.5)

        schema = gcs._build_field_schema("ratio", M.model_fields["ratio"])
        self.assertEqual(schema, {"type": "float", "description": "Ratio", "default": 1.5})

    def test_literal_field(self):
        class M(BaseModel):
            kind: Literal["x", "y", "z"]

        field = M.model_fields["kind"]
        effective = gcs.get_effective_type(field.annotation)
        # pure Literal -> string + options, no metadata applied
        schema = gcs._build_scalar_or_literal_schema(effective, field)
        self.assertEqual(schema, {"type": "string", "options": ["x", "y", "z"]})

    def test_literal_str_union_field(self):
        class M(BaseModel):
            val: Literal["a"] | str = Field(title="Val", default="a")

        schema = gcs._build_field_schema("val", M.model_fields["val"])
        self.assertEqual(
            schema,
            {"type": "string", "description": "Val", "default": "a"},
        )

    def test_int_field_with_slider(self):
        class M(BaseModel):
            score: int = Field(title="Score", ge=0, le=100, default=50)

        schema = gcs._build_field_schema("score", M.model_fields["score"])
        self.assertEqual(
            schema,
            {
                "type": "int",
                "slider": {"step": 1, "min": 0, "max": 100},
                "description": "Score",
                "default": 50,
            },
        )


# ============================================================================
#  model_to_schema tests
# ============================================================================


class SimpleModel(BaseModel):
    enabled: bool = Field(title="Enabled", default=True)
    count: int = Field(title="Count", ge=0, le=100, default=50)


class NestedOuter(BaseModel):
    class NestedInner(BaseModel):
        value: str = Field(title="V")

    inner: NestedInner = Field(title="Inner")
    name: str = Field(title="Name", default="")


class TestModelToSchema(unittest.TestCase):
    maxDiff = None

    def test_simple_model(self):
        schema = gcs.model_to_schema(SimpleModel)
        self.assertEqual(
            schema,
            {
                "enabled": {"type": "bool", "description": "Enabled", "default": True},
                "count": {
                    "type": "int",
                    "slider": {"step": 1, "min": 0, "max": 100},
                    "description": "Count",
                    "default": 50,
                },
            },
        )

    def test_nested_model(self):
        schema = gcs.model_to_schema(NestedOuter)
        self.assertEqual(
            schema,
            {
                "inner": {
                    "type": "object",
                    "items": {"value": {"type": "string", "description": "V"}},
                    "description": "Inner",
                },
                "name": {"type": "string", "description": "Name", "default": ""},
            },
        )

    def test_empty_model(self):
        class Empty(BaseModel):
            pass

        self.assertEqual(gcs.model_to_schema(Empty), {})


# ============================================================================
#  Full-pipeline ConfSchema validation test
# ============================================================================


class TestConfSchemaValidation(unittest.TestCase):
    """Integration tests: validate whole schema dicts against ConfSchema."""

    def test_simple_schema_passes(self):
        data = {
            "enabled": {"type": "bool", "default": True},
            "name": {"type": "string", "default": ""},
        }
        gcs.ConfSchema.model_validate(data)

    def test_object_with_items_passes(self):
        data = {
            "nested": {
                "type": "object",
                "items": {"x": {"type": "int", "default": 0}},
            }
        }
        gcs.ConfSchema.model_validate(data)

    def test_all_field_types_roundtrip(self):
        """Construct a schema using every AllFieldTypes variant and validate it."""
        data: dict[str, Any] = {
            "str_f": {"type": "string"},
            "text_f": {"type": "text"},
            "int_f": {"type": "int"},
            "float_f": {"type": "float"},
            "bool_f": {"type": "bool"},
            "object_f": {"type": "object", "items": {"sub": {"type": "bool"}}},
            "list_f": {"type": "list"},
            "dict_f": {"type": "dict", "template_schema": {"k": {"type": "string"}}},
            "file_f": {"type": "file"},
            "template_list_f": {
                "type": "template_list",
                "templates": {
                    "t1": {
                        "items": {"f": {"type": "string"}},
                    }
                },
            },
        }
        gcs.ConfSchema.model_validate(data)

    def test_generated_from_cfg_passes(self):
        """The real Config model must produce a schema that passes full validation."""
        schema = gcs.model_to_schema(gcs.cfg.Config)
        gcs.ConfSchema.model_validate(schema)

    def test_invalid_object_rejected(self):
        data = {"bad": {"type": "object"}}  # items=None
        with self.assertRaises(ValidationError):
            gcs.ConfSchema.model_validate(data)

    def test_invalid_default_rejected(self):
        data = {"bad": {"type": "string", "options": ["a"], "default": "b"}}
        with self.assertRaises(ValidationError):
            gcs.ConfSchema.model_validate(data)


if __name__ == "__main__":
    unittest.main()
