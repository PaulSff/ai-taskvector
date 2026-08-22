from typing import Any, TypeVar

from core.schemas import ProcessGraph

T = TypeVar("T")


def required[T](
    payload: dict[str, object],
    key: str,
    expected_type: type[T],
) -> T:
    value = payload.get(key)

    if not isinstance(value, expected_type):
        raise TypeError(
            f"payload[{key!r}] must be {expected_type.__name__}, got {type(value).__name__}"
        )

    return value


def optional[T](
    payload: dict[str, object],
    key: str,
    expected_type: type[T],
) -> T | None:
    value = payload.get(key)

    if value is None:
        return None

    if not isinstance(value, expected_type):
        raise TypeError(
            f"payload[{key!r}] must be {expected_type.__name__} or None, got {type(value).__name__}"
        )

    return value



def required_str(
    payload: dict[str, object],
    key: str,
) -> str:
    return required(payload, key, str)


def optional_str(
    payload: dict[str, object],
    key: str,
) -> str | None:
    return optional(payload, key, str)


def optional_bool(
    payload: dict[str, object],
    key: str,
) -> bool | None:
    return optional(payload, key, bool)


def optional_float(
    payload: dict[str, object],
    key: str,
) -> float | None:
    value = payload.get(key)

    if value is None:
        return None

    # bool is a subclass of int, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"payload[{key!r}] must be a number or None, got {type(value).__name__}"
        )

    return float(value)

def bool_or_default(
    payload: dict[str, object],
    key: str,
    default: bool = False,
) -> bool:
    value = payload.get(key, default)

    if not isinstance(value, bool):
        raise TypeError(
            f"payload[{key!r}] must be a bool, got {type(value).__name__}"
        )

    return value

def optional_process_graph(
    payload: dict[str, object],
    key: str,
) -> ProcessGraph | None:
    value = payload.get(key)

    if value is None:
        return None

    if not isinstance(value, ProcessGraph):
        raise TypeError(
            f"payload[{key!r}] must be a ProcessGraph or None, got {type(value).__name__}"
        )

    return value

def optional_dict(
    payload: dict[str, object],
    key: str,
) -> dict[str, Any] | None:
    value = payload.get(key)

    if value is None:
        return None

    if not isinstance(value, dict):
        raise TypeError(
            f"payload[{key!r}] must be a dict or None, got {type(value).__name__}"
        )

    return value

def required_dict(
    payload: dict[str, object],
    key: str,
) -> dict[str, Any]:
    value = payload.get(key)

    if not isinstance(value, dict):
        raise TypeError(
            f"payload[{key!r}] must be a dict, got {type(value).__name__}"
        )

    return value


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, dict):
        return not value or all(
            is_empty_value(nested_value)
            for nested_value in value.values()
        )

    if isinstance(value, (list, tuple, set)):
        return not value or all(
            is_empty_value(item)
            for item in value
        )

    # Values such as 0 and False are considered non-empty.
    return False
