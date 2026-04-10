"""
Validate workflow_designer role.yaml tools match assistants/tools/catalog.py
and every catalog tool registers a follow-up runner.

Run from repo root: python scripts/test_role_tools.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from assistants.roles import clear_role_cache, get_role
from assistants.tools.catalog import ORDERED_WORKFLOW_DESIGNER_TOOLS, workflow_designer_tool_ids
from assistants.tools.registry import get_follow_up_runner


def test_all_catalog_follow_up_runners_registered() -> None:
    for tool_id, _ in ORDERED_WORKFLOW_DESIGNER_TOOLS:
        r = get_follow_up_runner(tool_id)
        assert callable(r), f"{tool_id!r} must register an async follow-up runner"


def test_workflow_designer_role_tools_match_catalog() -> None:
    clear_role_cache()
    role = get_role("workflow_designer")
    expected = workflow_designer_tool_ids()
    assert role.tools == expected, (
        f"role.tools {role.tools!r} != catalog {expected!r}. "
        "Update assistants/roles/workflow_designer/role.yaml or catalog.py."
    )


def test_rl_coach_role_tools_empty_until_wired() -> None:
    """RL Coach has no parser-output follow-up allowlist today (Phase 4)."""
    clear_role_cache()
    role = get_role("rl_coach")
    assert role.tools == (), f"expected no rl_coach follow-up tools yet, got {role.tools!r}"


if __name__ == "__main__":
    test_all_catalog_follow_up_runners_registered()
    print("all catalog follow-up runners registered (ok)")
    test_workflow_designer_role_tools_match_catalog()
    print("workflow_designer role tools match catalog (ok)")
    test_rl_coach_role_tools_empty_until_wired()
    print("rl_coach role tools empty (ok)")
