from typing import Literal

type JsonPrimitive = str | int | float | bool | None
type JsonValue = (
    JsonPrimitive
    | list[JsonValue]
    | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]
type WorkflowInputs = dict[str, dict[str, JsonValue]]

FormatProcess = Literal[
    "yaml",
    "dict",
    "node_red",
    "template",
    "pyflow",
]
