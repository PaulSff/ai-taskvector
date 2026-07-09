from pathlib import Path
from typing import Any, Dict, Optional
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
default_conf = str(SCRIPT_DIR / "conf.yaml")


def load_conf_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("conf.yaml must be a YAML mapping/object at the root")
    return data


def get_conf_value(conf: Dict[str, Any], key: str, default: Any = None) -> Any:
    if key in conf:
        return conf[key]
    if default is not None:
        return default
    raise KeyError(f"Missing required key in conf.yaml: {key}")


def load_conf(
    path: Optional[str] = None,
    *,
    required_keys: Optional[list[str]] = None,
) -> Dict[str, Any]:
    conf_path = path or default_conf
    conf = load_conf_yaml(conf_path)
    if required_keys:
        missing = [k for k in required_keys if k not in conf]
        if missing:
            raise KeyError(f"Missing required keys in conf.yaml: {', '.join(missing)}")
    return conf


# ---- usage: load and expose your constants from conf.yaml ----

conf = load_conf(required_keys=[
    "metadata_str_max",
    "comments_max",
    "comment_info_max",
    "todo_tasks_max",
])

metadata_str_max: int = int(get_conf_value(conf, "metadata_str_max"))
comments_max: int = int(get_conf_value(conf, "comments_max"))
comment_info_max: int = int(get_conf_value(conf, "comment_info_max"))
todo_tasks_max: int = int(get_conf_value(conf, "todo_tasks_max"))
