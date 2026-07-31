import datetime


def _now_ts() -> str:
    """ISO-8601 timestamp (seconds precision)."""
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
