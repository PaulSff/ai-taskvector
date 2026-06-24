import datetime as dt
import json
import os
from pathlib import Path
from typing import (
    Any,
    Dict,
    Optional,
)

import yaml
from telegram import Message

SCRIPT_DIR = Path(__file__).resolve().parent
default_conf = str(SCRIPT_DIR / "conf.yaml")


def load_conf_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("conf.yaml must be a YAML mapping/object at the root")
    return data


def get_zmq_sub_endpoint(conf: Dict[str, Any]) -> str:
    if conf.get("ZMQ_SUB_ENDPOINT"):
        return str(conf["ZMQ_SUB_ENDPOINT"])
    if conf.get("zmq_sub_endpoint"):
        return str(conf["zmq_sub_endpoint"])
    if isinstance(conf.get("zmq_sub"), dict) and conf["zmq_sub"].get("endpoint"):
        return str(conf["zmq_sub"]["endpoint"])
    raise KeyError("Missing ZMQ_SUB_ENDPOINT in conf.yaml")


def get_zmq_pub_endpoint(conf: Dict[str, Any]) -> str:
    if conf.get("ZMQ_PUB_ENDPOINT"):
        return str(conf["ZMQ_PUB_ENDPOINT"])
    if conf.get("zmq_pub_endpoint"):
        return str(conf["zmq_pub_endpoint"])
    if isinstance(conf.get("zmq_pub"), dict) and conf["zmq_pub"].get("endpoint"):
        return str(conf["zmq_pub"]["endpoint"])
    raise KeyError("Missing ZMQ_PUB_ENDPOINT in conf.yaml")


def get_zmq_update_endpoint(conf: Dict[str, Any]) -> str:
    if conf.get("ZMQ_UPDATE_ENDPOINT"):
        return str(conf["ZMQ_UPDATE_ENDPOINT"])
    if conf.get("zmq_update_endpoint"):
        return str(conf["zmq_update_endpoint"])
    if isinstance(conf.get("zmq_update"), dict) and conf["zmq_update"].get("endpoint"):
        return str(conf["zmq_update"]["endpoint"])
    raise KeyError("Missing ZMQ_UPDATE_ENDPOINT in conf.yaml")


def _param_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _int_param(
    value: Any, *, default: int, minimum: int = 1, maximum: int = 1000
) -> int:
    try:
        n = int(value if value is not None else default)
    except (TypeError, ValueError):
        n = default
    return max(minimum, min(n, maximum))


def _ts_suffix_yy_dd_mm_ss(ts: Optional[float] = None) -> str:
    if ts is None:
        d = dt.datetime.now(dt.timezone.utc)
    else:
        d = dt.datetime.fromtimestamp(float(ts), tz=dt.timezone.utc)
    return (
        f"{d.strftime('%y')}.{d.strftime('%d')}.{d.strftime('%m')}.{d.strftime('%S')}"
    )


def _normalize_message_to_tdlib_shape(msg: Message) -> Dict[str, Any]:
    def to_int_or_none(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    chat_id = to_int_or_none(getattr(msg.chat, "id", None))
    msg_id = to_int_or_none(getattr(msg, "message_id", None))

    date_ts = None
    if getattr(msg, "date", None) is not None:
        try:
            date_ts = int(msg.date.timestamp())
        except Exception:
            date_ts = None

    text = msg.text or msg.caption or ""
    content: Dict[str, Any] = {"@type": "messageText", "text": {"text": text}}

    from_user: Dict[str, Any] | None = None
    fu = getattr(msg, "from_user", None)
    if fu is not None:
        fu_id = to_int_or_none(getattr(fu, "id", None))
        from_user = {"id": fu_id}
        if getattr(fu, "username", None) is not None:
            from_user["username"] = fu.username
        if getattr(fu, "first_name", None) is not None:
            from_user["first_name"] = fu.first_name

    message_obj: Dict[str, Any] = {
        "id": msg_id,
        "chat_id": chat_id,
        "content": content,
        "date": date_ts,
        "from": from_user,
    }
    return {"id": msg_id, "chat_id": chat_id, "message": message_obj}


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_atomic(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
