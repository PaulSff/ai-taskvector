"""
Validate workflow_designer role.yaml tools match agents/tools/catalog.py
and every catalog tool registers a follow-up runner.

Run from repo root: python scripts/test_role_tools.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from agents.chat.role_turns.turn_edits import canonicalize_add_comment_edits
from agents.roles import (
    CHAT_NAME_CREATOR_ROLE_ID,
    RL_COACH_ROLE_ID,
    WORKFLOW_DESIGNER_ROLE_ID,
    clear_role_cache,
    get_role,
    get_role_chat_workflow_path,
    list_chat_dropdown_role_ids,
    list_role_ids,
    role_chat_feature_enabled,
)
from agents.roles.chat_config import parse_role_chat_config
from agents.tools.registry import get_follow_up_runner
from agents.tools.workflow_path import get_tool_workflow_path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def test_follow_up_runners_registered_for_each_role() -> None:
    role_ids = list_role_ids()

    for role_id in role_ids:
        role = get_role(role_id)

        # role.tools is already a tuple[str, ...] in RoleConfig
        for tool_id in role.tools:
            runner = get_follow_up_runner(tool_id)
            assert callable(runner), (
                f"role {role_id!r}: tool {tool_id!r} must register an async follow-up runner"
            )

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
    cnc = get_role_chat_workflow_path(CHAT_NAME_CREATOR_ROLE_ID)
    assert cnc.is_file(), f"missing chat_name_creator workflow: {cnc}"
    assert CHAT_NAME_CREATOR_ROLE_ID in list_role_ids()


def test_tool_yaml_workflow_paths_exist() -> None:
    for tid in (
        "add_comment",
        "web_search",
        "browse",
        "github",
        "grep",
        "rag_search",
        "run_workflow",
        "run_rl_training",
        "read_file",
        "formulas_calc",
        "read_code_block",
        "read_current_workflow",
        "todo_manager",
        "get_chats",
        "send_message",
    ):
        p = get_tool_workflow_path(tid)
        assert p.is_file(), f"missing tool workflow for {tid!r}: {p}"


def test_role_chat_feature_flags() -> None:
    clear_role_cache()
    wd = get_role(WORKFLOW_DESIGNER_ROLE_ID)
    assert role_chat_feature_enabled(wd.chat, "graph_canvas", default=True) is True
    rl = get_role(RL_COACH_ROLE_ID)
    assert role_chat_feature_enabled(rl.chat, "graph_canvas", default=True) is False
    assert role_chat_feature_enabled(None, "graph_canvas", default=True) is True


async def test_canonicalize_add_comment_edits() -> None:
    edits = [
        {"action": "add_comment", "info": "hello", "commenter": "fake_role"},
        {"action": "add_unit", "unit": {"id": "u1", "type": "sink"}},
    ]
    await canonicalize_add_comment_edits(edits, agent_role_id="workflow_designer")
    assert edits[0]["commenter"] == "workflow_designer"
    assert edits[0]["info"] == "hello"


def test_parse_chat_handler_spec() -> None:
    cfg = parse_role_chat_config(
        {"enabled": True, "handler": "some.package:MyHandler", "features": {"x": True}}
    )
    assert cfg is not None
    assert cfg.chat_handler == "some.package:MyHandler"
    assert cfg.features.get("x") is True


if __name__ == "__main__":
    test_follow_up_runners_registered_for_each_role()
    print("all catalog follow-up runners registered (ok)")
    test_role_yaml_chat_block()
    print("role.yaml chat blocks parse (ok)")
    test_list_chat_dropdown_role_ids_order()
    print("list_chat_dropdown_role_ids order (ok)")
    test_role_chat_workflow_paths_exist()
    print("role chat workflow paths exist (ok)")
    test_tool_yaml_workflow_paths_exist()
    print("tool.yaml workflow paths exist (ok)")
    test_role_chat_feature_flags()
    print("role chat feature flags (ok)")
    asyncio.run(test_canonicalize_add_comment_edits())
    print("canonicalize add_comment edits (ok)")
    print("canonicalize add_comment edits (ok)")
    test_parse_chat_handler_spec()
    print("parse chat.handler (ok)")
