"""
Shared types for assistant follow-up tools (Phase 2+).

Tool runners consume normalized parser output and a narrow follow-up context protocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Keys for ``FollowUpContribution.extra`` merged by the Workflow Designer orchestrator.
FOLLOW_UP_EXTRA_READ_CODE_IDS = "read_code_ids_for_msg"
FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES = "implementation_links_for_types"


@dataclass
class FollowUpContribution:
    """Result of running one tool in a follow-up round."""

    context_chunks: list[str] = field(default_factory=list)
    any_empty_tool: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
