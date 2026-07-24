from uuid import uuid4


def _new_id() -> str:
    return uuid4().hex
