"""Out-of-band UI signals sent on the same stream_callback channel as LLM tokens (worker thread → async consumer)."""

# Unlikely to appear in normal UTF-8 model output.
INLINE_STATUS_PREFIX = "\xff\xfeflet_inline_status\xff\xfe"


def inline_status_stream_chunk(message: str | None) -> str:
    """Build a chunk the chat consumer treats as inline status, not assistant text. Empty / None clears."""
    return INLINE_STATUS_PREFIX + (message or "")
