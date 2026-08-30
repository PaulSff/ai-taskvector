from pathlib import Path
from typing import cast

import yaml

from core.schemas.primitives import is_string_keyed_dict

SCRIPT_DIR = Path(__file__).resolve().parent
default_conf = SCRIPT_DIR / "conf.yaml"


def load_conf_yaml(path: str | Path) -> dict[str, object]:
    with open(path, "r", encoding="utf-8") as f:
        loaded: object = cast(object, yaml.safe_load(f))

    if loaded is None:
        return {}

    if not is_string_keyed_dict(loaded):
        raise TypeError(
            "conf.yaml must be a YAML mapping with string keys at the root"
        )

    return loaded


def get_conf_value(
    conf: dict[str, object],
    key: str,
    default: object | None = None,
) -> object:
    if key in conf:
        return conf[key]

    if default is not None:
        return default

    raise KeyError(f"Missing required key in conf.yaml: {key}")


def get_conf_int(conf: dict[str, object], key: str) -> int:
    value = get_conf_value(conf, key)

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Configuration key {key!r} must be an integer")

    return value


def get_conf_str_list(conf: dict[str, object], key: str) -> list[str]:
    value = get_conf_value(conf, key)

    if not isinstance(value, list):
        raise TypeError(f"Configuration key {key!r} must be a list")

    items = cast(list[object], value)

    if not all(isinstance(item, str) for item in items):
        raise TypeError(
            f"Configuration key {key!r} must contain only strings"
        )

    return cast(list[str], items)


def get_conf_str_dict(conf: dict[str, object], key: str) -> dict[str, str]:
    value = get_conf_value(conf, key)

    if not isinstance(value, dict):
        raise TypeError(f"Configuration key {key!r} must be a mapping")

    items = cast(dict[object, object], value)

    if not all(
        isinstance(item_key, str) and isinstance(item_value, str)
        for item_key, item_value in items.items()
    ):
        raise TypeError(
            f"Configuration key {key!r} must map strings to strings"
        )

    return {
        cast(str, item_key): cast(str, item_value)
        for item_key, item_value in items.items()
    }


def load_conf(
    path: str | Path | None = None,
    *,
    required_keys: list[str] | None = None,
) -> dict[str, object]:
    conf_path = path or default_conf
    conf = load_conf_yaml(conf_path)

    if required_keys:
        missing = [key for key in required_keys if key not in conf]
        if missing:
            raise KeyError(
                f"Missing required keys in conf.yaml: {', '.join(missing)}"
            )

    return conf


conf = load_conf(
    required_keys=[
        "metadata_str_max",
        "comments_max",
        "comment_info_max",
        "todo_tasks_max",
        "valid_origin",
        "origin_language",
        "custom_code_unit_types",
    ],
)

metadata_str_max = get_conf_int(conf, "metadata_str_max")
comments_max = get_conf_int(conf, "comments_max")
comment_info_max = get_conf_int(conf, "comment_info_max")
todo_tasks_max = get_conf_int(conf, "todo_tasks_max")
valid_origin = get_conf_str_list(conf, "valid_origin")

CUSTOM_CODE_UNIT_TYPES = frozenset(
    get_conf_str_list(conf, "custom_code_unit_types")
)

ORIGIN_LANGUAGE = get_conf_str_dict(conf, "origin_language")
