"""
Tests for Aggregate and Prompt canonical units (aggregation, user_message fallback, template substitution).

Run from repo root:
  python scripts/test_merge_prompt.py
  pytest scripts/test_merge_prompt.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from units.registry import get_unit_spec
from units.canonical.aggregate import register_merge
from units.canonical.prompt import register_prompt


def _ensure_registered() -> None:
    register_merge()
    register_prompt()


# ---- Merge unit tests ----


def test_merge_pass_through_when_data_is_dict() -> None:
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None
    prebuilt = {"user_message": "hello", "graph_summary": "units: []"}
    outputs, state = spec.step_fn(
        {},
        {"data": prebuilt},
        {},
        0.0,
    )
    assert outputs["data"] is prebuilt
    assert outputs["data"]["user_message"] == "hello"
    assert outputs.get("error", "").strip() == ""


def test_merge_aggregates_in_ports_with_keys() -> None:
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None
    params = {
        "num_inputs": 3,
        "keys": ["user_message", "graph_summary", "units_library"],
    }
    inputs = {
        "in_0": "Add a valve",
        "in_1": '{"units": []}',
        "in_2": "Units: Valve, Tank",
    }
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    data = outputs["data"]
    assert data["user_message"] == "Add a valve"
    assert data["graph_summary"] == '{"units": []}'
    assert data["units_library"] == "Units: Valve, Tank"


def test_merge_none_inputs_become_empty_string() -> None:
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None
    params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}
    inputs = {"in_0": "Hi", "in_1": None}  # in_1 missing/None
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    data = outputs["data"]
    assert data["user_message"] == "Hi"
    assert data["graph_summary"] == ""


def test_merge_empty_user_message_replaced_with_placeholder() -> None:
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None
    params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}
    inputs = {"in_0": "", "in_1": "summary"}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    data = outputs["data"]
    assert data["user_message"] == "(No message provided.)"
    assert data["graph_summary"] == "summary"
    # Required user_message is missing → error port set
    assert "user_message" in (outputs.get("error") or "")


def test_merge_whitespace_only_user_message_replaced() -> None:
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None
    params = {"num_inputs": 1, "keys": ["user_message"]}
    inputs = {"in_0": "   \n\t  "}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    assert outputs["data"]["user_message"] == "(No message provided.)"
    assert "user_message" in (outputs.get("error") or "")


def test_merge_string_data_not_passthrough() -> None:
    """When 'data' input is a string (e.g. mistaken wiring), do not pass-through; aggregate in_* instead."""
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None
    inputs = {"data": "oops string", "in_0": "real message", "in_1": "summary"}
    params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    data = outputs["data"]
    assert "user_message" in data
    assert data["user_message"] == "real message"
    assert data["graph_summary"] == "summary"
    assert (outputs.get("error") or "").strip() == ""


def test_merge_error_port_when_required_keys_missing() -> None:
    """Error port is set when a required key (e.g. user_message) is missing or placeholder."""
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None
    params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"], "required_keys": ["user_message"]}
    inputs = {"in_0": "(No message provided.)", "in_1": "summary"}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    assert "Aggregate:" in (outputs.get("error") or "")
    assert "user_message" in (outputs.get("error") or "")
    params_ok = {"num_inputs": 2, "keys": ["user_message", "graph_summary"], "required_keys": ["user_message"]}
    inputs_ok = {"in_0": "real request", "in_1": "summary"}
    outputs_ok, _ = spec.step_fn(params_ok, inputs_ok, {}, 0.0)
    assert (outputs_ok.get("error") or "").strip() == ""


# ---- Prompt unit tests ----


def test_prompt_substitutes_template() -> None:
    _ensure_registered()
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None
    params = {"template": "You are {role}. User said: {user_message}"}
    inputs = {"data": {"role": "Assistant", "user_message": "Hello"}}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    assert "Assistant" in outputs["system_prompt"]
    assert "Hello" in outputs["system_prompt"]
    assert outputs["user_message"] == "Hello"


def test_prompt_empty_user_message_replaced() -> None:
    _ensure_registered()
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None
    params = {"template": "Role: {role}"}
    inputs = {"data": {"role": "Helper", "user_message": ""}}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    assert outputs["user_message"] == "(No message provided.)"


def test_prompt_missing_user_message_replaced() -> None:
    _ensure_registered()
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None
    params = {"template": "Hi"}
    inputs = {"data": {"graph_summary": "empty"}}  # no user_message key
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    assert outputs["user_message"] == "(No message provided.)"


def test_prompt_non_dict_data_treated_as_empty() -> None:
    _ensure_registered()
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None
    params = {"template": "Static"}
    inputs = {"data": None}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    assert outputs["system_prompt"] == "Static"
    assert outputs["user_message"] == "(No message provided.)"


def test_prompt_format_keys_json_dumps_value() -> None:
    _ensure_registered()
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None
    params = {"template": "Graph: {graph_summary}", "format_keys": ["graph_summary"]}
    inputs = {"data": {"user_message": "Hi", "graph_summary": {"units": [{"id": "a"}]}}}
    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    assert "units" in outputs["system_prompt"]
    assert '"id": "a"' in outputs["system_prompt"] or '"id":\'a\'' in outputs["system_prompt"]


# ---- Merge → Prompt integration ----

def test_merge_then_prompt_user_message_flows() -> None:
    """Merge aggregates; Prompt receives and forwards user_message. Empty user_message becomes placeholder."""
    _ensure_registered()
    merge_spec = get_unit_spec("Aggregate")
    prompt_spec = get_unit_spec("Prompt")
    assert merge_spec and merge_spec.step_fn and prompt_spec and prompt_spec.step_fn

    merge_params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}
    merge_inputs = {"in_0": "Add a valve", "in_1": "summary"}
    merge_out, _ = merge_spec.step_fn(merge_params, merge_inputs, {}, 0.0)
    merged_data = merge_out["data"]

    prompt_params = {"template": "Graph: {graph_summary}"}
    prompt_inputs = {"data": merged_data}
    prompt_out, _ = prompt_spec.step_fn(prompt_params, prompt_inputs, {}, 0.0)

    assert prompt_out["user_message"] == "Add a valve"
    assert "summary" in prompt_out["system_prompt"]


def test_merge_then_prompt_empty_user_message_becomes_placeholder() -> None:
    """If Merge gets empty user_message, both Merge and Prompt ensure placeholder to LLM."""
    _ensure_registered()
    merge_spec = get_unit_spec("Aggregate")
    prompt_spec = get_unit_spec("Prompt")
    assert merge_spec and merge_spec.step_fn and prompt_spec and prompt_spec.step_fn

    merge_params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}
    merge_inputs = {"in_0": "", "in_1": "graph"}
    merge_out, _ = merge_spec.step_fn(merge_params, merge_inputs, {}, 0.0)
    prompt_inputs = {"data": merge_out["data"]}
    prompt_out, _ = prompt_spec.step_fn({"template": "Hi"}, prompt_inputs, {}, 0.0)

    assert prompt_out["user_message"] == "(No message provided.)"


# ---- Full prompt / LLM agent receives full prompt ----

def test_prompt_full_system_prompt_all_placeholders_filled() -> None:
    """Prompt fills all template placeholders; system_prompt is complete."""
    _ensure_registered()
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None
    template = (
        "Role: {role}. Turn: {turn_state}. "
        "Graph: {graph_summary}. User: {user_message}."
    )
    data = {
        "role": "Workflow Designer",
        "turn_state": "Last action: none.",
        "graph_summary": '{"units": [{"id": "a"}]}',
        "user_message": "Add a valve",
    }
    outputs, _ = spec.step_fn({"template": template}, {"data": data}, {}, 0.0)
    sp = outputs["system_prompt"]
    assert "Workflow Designer" in sp
    assert "Last action: none." in sp
    assert "Add a valve" in sp
    assert '{"units"' in sp or "units" in sp
    assert outputs["user_message"] == "Add a valve"


def test_prompt_workflow_designer_template_produces_full_prompt() -> None:
    """Load real workflow_designer.json; merged data produces full system_prompt and user_message for LLM agent."""
    _ensure_registered()
    template_path = REPO_ROOT / "config" / "prompts" / "workflow_designer.json"
    if not template_path.is_file():
        return  # skip if template not in repo
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None
    # Data shape matching merge_llm output (keys from assistant_workflow merge_llm).
    merged_data = {
        "user_message": "Add a Valve unit and connect it to the tank",
        "graph_summary": {"units": [{"id": "tank", "type": "Tank"}], "connections": []},
        "units_library": "Valve, Tank, Sensor...",
        "rag_context": "",
        "turn_state": "Turn state: Last action: none.",
        "recent_changes_block": "",
        "last_edit_block": "",
        "follow_up_context": "",
    }
    params = {"template_path": str(template_path)}
    outputs, _ = spec.step_fn(params, {"data": merged_data}, {}, 0.0)
    system_prompt = outputs["system_prompt"]
    user_message = outputs["user_message"]
    # LLM agent must receive non-empty, substantial system prompt
    assert len(system_prompt) > 200, "system_prompt should be full (template + substituted data)"
    assert "Workflow Designer" in system_prompt
    assert "Current process graph" in system_prompt or "graph" in system_prompt.lower()
    # User message must be passed through for the LLM
    assert user_message == "Add a Valve unit and connect it to the tank"
    assert "user_message" in outputs


def test_merge_prompt_llm_agent_receives_full_prompt() -> None:
    """Merge (8 keys) → Prompt (workflow_designer template) → outputs are what LLM agent receives."""
    _ensure_registered()
    template_path = REPO_ROOT / "config" / "prompts" / "workflow_designer.json"
    if not template_path.is_file():
        return
    merge_spec = get_unit_spec("Aggregate")
    prompt_spec = get_unit_spec("Prompt")
    assert merge_spec and merge_spec.step_fn and prompt_spec and prompt_spec.step_fn

    merge_params = {
        "num_inputs": 8,
        "keys": [
            "user_message",
            "graph_summary",
            "units_library",
            "rag_context",
            "turn_state",
            "recent_changes_block",
            "last_edit_block",
            "follow_up_context",
        ],
    }
    graph_summary = {"units": [{"id": "src", "type": "Source"}], "connections": []}
    merge_inputs = {
        "in_0": "I want to add a valve",
        "in_1": graph_summary,
        "in_2": "Units: Valve, Tank, Sensor",
        "in_3": "",
        "in_4": "Turn state: Last action: none.",
        "in_5": "",
        "in_6": "",
        "in_7": "",
    }
    merge_out, _ = merge_spec.step_fn(merge_params, merge_inputs, {}, 0.0)
    merged_data = merge_out["data"]
    assert merged_data["user_message"] == "I want to add a valve"

    prompt_params = {"template_path": str(template_path)}
    prompt_out, _ = prompt_spec.step_fn(
        prompt_params, {"data": merged_data}, {}, 0.0
    )
    # These are the two inputs the LLMAgent unit receives (system_prompt, user_message).
    system_prompt = prompt_out["system_prompt"]
    user_message = prompt_out["user_message"]

    assert len(system_prompt) > 100, "LLM agent must receive full system prompt"
    assert "Workflow Designer" in system_prompt
    assert user_message == "I want to add a valve", "LLM agent must receive user message"
    assert "system_prompt" in prompt_out and "user_message" in prompt_out


if __name__ == "__main__":
    _ensure_registered()
    # Run tests manually for simple invocation without pytest
    test_merge_pass_through_when_data_is_dict()
    test_merge_aggregates_in_ports_with_keys()
    test_merge_none_inputs_become_empty_string()
    test_merge_empty_user_message_replaced_with_placeholder()
    test_merge_whitespace_only_user_message_replaced()
    test_merge_string_data_not_passthrough()
    test_prompt_substitutes_template()
    test_prompt_empty_user_message_replaced()
    test_prompt_missing_user_message_replaced()
    test_prompt_non_dict_data_treated_as_empty()
    test_prompt_format_keys_json_dumps_value()
    test_merge_then_prompt_user_message_flows()
    test_merge_then_prompt_empty_user_message_becomes_placeholder()
    test_prompt_full_system_prompt_all_placeholders_filled()
    test_prompt_workflow_designer_template_produces_full_prompt()
    test_merge_prompt_llm_agent_receives_full_prompt()
    print("All tests passed.")
