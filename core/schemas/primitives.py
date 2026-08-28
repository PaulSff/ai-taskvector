from typing import Literal, Protocol, TypeGuard, cast, runtime_checkable

type JsonPrimitive = str | int | float | bool | None
type JsonValue = (
    JsonPrimitive
    | list[JsonValue]
    | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]
type WorkflowInputs = dict[str, dict[str, JsonValue]]
# Workflow output is always the JsonObject

FormatProcess = Literal[
    "yaml",
    "dict",
    "node_red",
    "template",
    "pyflow",
]

@runtime_checkable
class ModelDumpable(Protocol):
    def model_dump(self, *, by_alias: bool = ...) -> JsonObject:
        ...

def is_format_process(
    value: object,
) -> TypeGuard[FormatProcess]:
    return value in {
        "yaml",
        "dict",
        "node_red",
        "template",
        "pyflow",
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
