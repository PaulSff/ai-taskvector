import datetime


def _now_ts() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
