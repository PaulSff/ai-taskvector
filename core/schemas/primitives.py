from __future__ import annotations

from typing import (
    Literal,
    Protocol,
    TypeGuard,
    cast,
    runtime_checkable,
)

type JsonPrimitive = str | int | float | bool | None
type JsonValue = (
    JsonPrimitive
    | list[JsonValue]
    | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]
type JsonArray = list[JsonValue]
type JsonDocument = JsonObject | JsonArray

type Data = dict[str, object]
type Output = tuple[Data, Data] | Data

type WorkflowInputs = dict[str, dict[str, JsonValue]]
type WorkflowOutputs = JsonObject
type WorkflowErrors = list[tuple[str, str]]

# Raw input format for any workflow to be normalized into ProcessGraph
RawProcessInput = JsonDocument | str

FormatProcess = Literal[
   "yaml",
   "dict",
   "node_red",
   "template",
   "pyflow",
   "ryven",
   "idaes",
   "n8n",
   "comfyui"
]

FormatTraining = Literal["yaml", "dict"]


@runtime_checkable
class ModelDumpable(Protocol):
    def model_dump(self, *, by_alias: bool = ...) -> JsonObject:
        ...

def is_format_process(value: object) -> TypeGuard[FormatProcess]:
    return value in {
        "yaml",
        "dict",
        "node_red",
        "template",
        "pyflow",
        "ryven",
        "idaes",
        "n8n",
        "comfyui",
    }

def is_json_value(value: object) -> TypeGuard[JsonValue]:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True

    if isinstance(value, list):
        items = cast(list[object], value)
        return all(is_json_value(item) for item in items)

    if isinstance(value, dict):
        values = cast(dict[object, object], value)

        return all(
            isinstance(key, str) and is_json_value(nested_value)
            for key, nested_value in values.items()
        )

    return False

def is_json_array(value: object) -> TypeGuard[list[JsonValue]]:
    if not is_json_value(value):
        return False

    return isinstance(value, list)

def is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False

    values = cast(dict[object, object], value)

    return all(
        isinstance(key, str) and is_json_value(nested_value)
        for key, nested_value in values.items()
    )

def is_model_dumpable(value: object) -> TypeGuard[ModelDumpable]:
    model_dump = getattr(value, "model_dump", None)
    return callable(model_dump)


def is_string(value: object) -> TypeGuard[str]:
    return isinstance(value, str)


def is_string_keyed_dict(
    value: object,
) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False

    items = cast(dict[object, object], value)

    return all(isinstance(key, str) for key in items)

def is_json_object_keyed_dict(
    value: JsonValue,
) -> TypeGuard[dict[str, JsonValue]]:
    return isinstance(value, dict)


def safe_int(value: object) -> int | None:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None

    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None

def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True

    if isinstance(value, list):
        items = cast(list[object], value)
        return all(_is_json_value(item) for item in items)

    if isinstance(value, dict):
        items = cast(dict[object, object], value)
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in items.items()
        )

    return False


def is_json_document(value: object) -> TypeGuard[JsonDocument]:
    if isinstance(value, dict):
        return _is_json_value(cast(dict[object, object], value))

    if isinstance(value, list):
        return _is_json_value(cast(list[object], value))

    return False


def is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)
