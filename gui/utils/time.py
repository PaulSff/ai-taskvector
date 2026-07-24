from datetime import datetime


def _now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")
