def _new_id() -> str:
    """uuid4 hex string."""
    from uuid import uuid4

    return uuid4().hex
