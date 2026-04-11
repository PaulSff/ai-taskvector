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

from assistants.roles import (
    RL_COACH_ROLE_ID,
    WORKFLOW_DESIGNER_ROLE_ID,
    clear_role_cache,
    get_role,
    get_role_chat_workflow_path,
    list_chat_dropdown_role_ids,
    role_chat_feature_enabled,
)
from assistants.roles.chat_config import parse_role_chat_config
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


def test_role_yaml_chat_block() -> None:
    clear_role_cache()
    wd = get_role("workflow_designer")
    assert wd.chat is not None and wd.chat.enabled is True
    assert (wd.chat.workflow or "").endswith(".json")
    rl = get_role("rl_coach")
    assert rl.chat is not None and rl.chat.enabled is True


def test_list_chat_dropdown_role_ids_order() -> None:
    clear_role_cache()
    ids = list_chat_dropdown_role_ids()
    assert WORKFLOW_DESIGNER_ROLE_ID in ids and RL_COACH_ROLE_ID in ids
    assert ids.index(WORKFLOW_DESIGNER_ROLE_ID) < ids.index(RL_COACH_ROLE_ID)


def test_role_chat_workflow_paths_exist() -> None:
    clear_role_cache()
    wd = get_role_chat_workflow_path(WORKFLOW_DESIGNER_ROLE_ID)
    rl = get_role_chat_workflow_path(RL_COACH_ROLE_ID)
    assert wd.is_file(), f"missing WD workflow: {wd}"
    assert rl.is_file(), f"missing RL workflow: {rl}"


def test_role_chat_feature_flags() -> None:
    clear_role_cache()
    wd = get_role(WORKFLOW_DESIGNER_ROLE_ID)
    assert role_chat_feature_enabled(wd.chat, "graph_canvas", default=True) is True
    rl = get_role(RL_COACH_ROLE_ID)
    assert role_chat_feature_enabled(rl.chat, "graph_canvas", default=True) is False
    assert role_chat_feature_enabled(None, "graph_canvas", default=True) is True


def test_parse_chat_handler_spec() -> None:
    cfg = parse_role_chat_config(
        {"enabled": True, "handler": "some.package:MyHandler", "features": {"x": True}}
    )
    assert cfg is not None
    assert cfg.chat_handler == "some.package:MyHandler"
    assert cfg.features.get("x") is True


if __name__ == "__main__":
    test_all_catalog_follow_up_runners_registered()
    print("all catalog follow-up runners registered (ok)")
    test_workflow_designer_role_tools_match_catalog()
    print("workflow_designer role tools match catalog (ok)")
    test_rl_coach_role_tools_empty_until_wired()
    print("rl_coach role tools empty (ok)")
    test_role_yaml_chat_block()
    print("role.yaml chat blocks parse (ok)")
    test_list_chat_dropdown_role_ids_order()
    print("list_chat_dropdown_role_ids order (ok)")
    test_role_chat_workflow_paths_exist()
    print("role chat workflow paths exist (ok)")
    test_role_chat_feature_flags()
    print("role chat feature flags (ok)")
    test_parse_chat_handler_spec()
    print("parse chat.handler (ok)")
