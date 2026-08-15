import datetime


def now_ts() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
