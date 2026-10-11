# Streaming Bubble Length Limit Implementation

Implemented a visual truncation mechanism for the chat streaming bubble to improve UI stability during long responses.


## Technical Changes

1. Defined `STREAMING_MAX_LENGTH` in `gui/components/chat_panel/chat.py`.
2. Updated `_stream_cb` to truncate text/rich content exceeding the limit.
3. Added ellipsis suffix to truncated content for visual clarity.


## Verification

Confirmed that only the temporary streaming state is truncated, while the final message state retains the full original content.
