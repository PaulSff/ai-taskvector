# role_handler_interface.py
"""
Typed Protocol for handling streaming message chunks.

Designed to be agnostic of UI framework — only assumes:
- `append_chunk(text: str)` → accumulate
- `finalize()` → get final message dict (e.g., {"role": "...", "content": "..."})
- Stateful, per-turn
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class StreamingMetadata:
    """Optional metadata carried across chunks (e.g., first chunk includes role)."""

    role: Optional[str] = None
    turn_id: Optional[str] = None
    # Expand as needed


@runtime_checkable
class RoleHandler(Protocol):
    """Protocol for stream-aware message handlers."""

    def begin_stream(self, meta: StreamingMetadata) -> None: ...

    """Called once at the start of a streaming turn."""

    def append_chunk(self, chunk: str) -> None: ...

    """Accumulate content from a streaming chunk."""

    def finalize(self) -> Optional[Dict[str, Any]]:
        """Called at stream end. Returns message payload or None if no finalization."""
        ...


# ─── Example: Simple text-only handler (current behavior) ─────────────────────
class PlainTextHandler:
    def __init__(self):
        self.content = ""
        self.role: str = "user"  # fallback (user doesn't stream)
        self.turn_id: str | None = None

    def begin_stream(self, meta: StreamingMetadata) -> None:
        self.role = meta.role or self.role
        self.turn_id = meta.turn_id

    def append_chunk(self, chunk: str) -> None:
        self.content += chunk

    def finalize(self) -> Optional[Dict[str, Any]]:
        if not self.content.strip():
            return None
        return {
            "role": self.role,
            "content": self.content,
            "turn_id": self.turn_id,
        }


# ─── Example: Rich-content handler (code fences, markdown, etc.) ──────────────
class RichTextHandler:
    def __init__(
        self,
        *,
        on_open_code_fence: bool = False,
        code_fence_language: Optional[str] = None,
        on_close_code_fence: bool = False,
    ):
        self.content = ""
        self.in_code_block = False
        self.code_fence_lang = ""
        self.role = "user"
        self.turn_id: str | None = None

    def begin_stream(self, meta: StreamingMetadata) -> None:
        self.role = meta.role or "assistant"
        self.turn_id = meta.turn_id
        self.in_code_block = False
        self.content = ""

    def append_chunk(self, chunk: str) -> None:
        # naive fence detection
        if chunk.startswith("```") and not self.in_code_block:
            self.in_code_block = True
            self.code_fence_lang = chunk[3:].strip() or "python"
            # keep opening line as content if needed
            self.content += chunk
        elif chunk.startswith("```") and self.in_code_block:
            self.in_code_block = False
            self.content += chunk
        else:
            self.content += chunk

    def finalize(self) -> Optional[Dict[str, Any]]:
        if not self.content.strip():
            return None
        return {
            "role": self.role,
            "content": self.content,
            "turn_id": self.turn_id,
            "rich_mode": True,  # marker for renderer
        }


# ─── Example: Mock for unit tests ─────────────────────────────────────────────
class MockHandler:
    def __init__(self):
        self.calls: list[str] = []
        self.final_result: Optional[Dict[str, Any]] = {
            "role": "mock",
            "content": "mocked",
        }

    def begin_stream(self, meta: StreamingMetadata) -> None:
        self.calls.append("begin")

    def append_chunk(self, chunk: str) -> None:
        self.calls.append(f"chunk:{chunk[:10]}...")

    def finalize(self) -> Optional[Dict[str, Any]]:
        self.calls.append("finalize")
        return self.final_result
