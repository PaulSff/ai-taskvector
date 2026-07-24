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
    "update_interval_s",
    "messenger",
    "max_workers",
    "default_max_concurrency",
    "lock_file_path",
    "zmq_tg_update_sub_endpoint",
])

update_interval_s: int = int(get_conf_value(conf, "update_interval_s"))
messenger: str = str(get_conf_value(conf, "messenger"))
max_workers: int = int(get_conf_value(conf, "max_workers"))
default_max_concurrency: int = int(get_conf_value(conf, "default_max_concurrency"))
lock_file_path: str = str(get_conf_value(conf, "lock_file_path"))
zmq_tg_update_sub_endpoint: str = str(get_conf_value(conf, "zmq_tg_update_sub_endpoint"))
