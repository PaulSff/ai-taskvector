"""
Tests for Aggregate and Prompt canonical units (aggregation, template substitution).

Aggregate collects ``in_*`` into ``data`` keyed by ``params.keys``; empty strings stay empty.
The Prompt unit applies the ``(No message provided.)`` fallback for ``user_message`` when absent or blank.

Run from repo root:
  python scripts/test_merge_prompt.py
  pytest scripts/test_merge_prompt.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

from units.canonical.aggregate import register_aggregate
from units.registry import get_unit_spec
from units.taskvector.prompt import register_prompt

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _ensure_registered() -> None:
    register_aggregate()
    register_prompt()


# ---- Merge unit tests ----


def test_merge_pass_through_when_data_is_dict() -> None:
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None

    prebuilt = {"user_message": "hello", "graph_summary": "units: []"}
    outputs, _ = spec.step_fn(
        {},
        {"data": prebuilt},
        {},
        0.0,
    )

    data = outputs["data"]
    assert isinstance(data, dict)
    assert data is prebuilt
    assert data["user_message"] == "hello"

    error = outputs.get("error", "")
    assert isinstance(error, str)
    assert error.strip() == ""


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
    assert isinstance(data, dict)
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
    assert isinstance(data, dict)
    assert data["user_message"] == "Hi"
    assert data["graph_summary"] == ""


def test_merge_empty_user_message_stays_empty_string() -> None:
    """Aggregate does not substitute placeholders; it stores empty ``in_0`` as ""."""
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None

    params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}
    inputs = {"in_0": "", "in_1": "summary"}

    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    data = outputs["data"]
    assert isinstance(data, dict)
    assert data["user_message"] == ""
    assert data["graph_summary"] == "summary"

    error = outputs.get("error", "")
    assert isinstance(error, str)
    assert error.strip() == ""


def test_merge_whitespace_only_user_message_passthrough() -> None:
    """Without ``required_keys``, Aggregate keeps whitespace-only strings as-is."""
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None

    params = {"num_inputs": 1, "keys": ["user_message"]}
    raw = "   \n\t  "
    inputs = {"in_0": raw}

    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    data = outputs["data"]
    assert isinstance(data, dict)
    assert data["user_message"] == raw

    error = outputs.get("error", "")
    assert isinstance(error, str)
    assert error.strip() == ""


def test_merge_string_data_not_passthrough() -> None:
    """When 'data' input is a string, aggregate the ``in_*`` inputs instead."""
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None

    inputs = {"data": "oops string", "in_0": "real message", "in_1": "summary"}
    params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}

    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    data = outputs["data"]
    assert isinstance(data, dict)
    assert "user_message" in data
    assert data["user_message"] == "real message"
    assert data["graph_summary"] == "summary"

    error = outputs.get("error", "")
    assert isinstance(error, str)
    assert error.strip() == ""


def test_merge_error_port_when_required_keys_missing() -> None:
    """With ``required_keys``, error is set when a required slot is empty or whitespace-only."""
    _ensure_registered()
    spec = get_unit_spec("Aggregate")
    assert spec is not None and spec.step_fn is not None

    params = {
        "num_inputs": 2,
        "keys": ["user_message", "graph_summary"],
        "required_keys": ["user_message"],
    }

    for empty_val in ("", "   \n"):
        inputs = {"in_0": empty_val, "in_1": "summary"}
        outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
        err = outputs.get("error", "")
        assert isinstance(err, str)
        assert "Aggregate:" in err
        assert "user_message" in err

    # Literal placeholder text is non-empty for ``_is_empty`` — no error.
    inputs_literal = {"in_0": "(No message provided.)", "in_1": "summary"}
    out_lit, _ = spec.step_fn(params, inputs_literal, {}, 0.0)
    literal_error = out_lit.get("error", "")
    assert isinstance(literal_error, str)
    assert literal_error.strip() == ""

    params_ok = {
        "num_inputs": 2,
        "keys": ["user_message", "graph_summary"],
        "required_keys": ["user_message"],
    }
    inputs_ok = {"in_0": "real request", "in_1": "summary"}
    outputs_ok, _ = spec.step_fn(params_ok, inputs_ok, {}, 0.0)
    ok_error = outputs_ok.get("error", "")
    assert isinstance(ok_error, str)
    assert ok_error.strip() == ""


# ---- Prompt unit tests ----


def test_prompt_substitutes_template() -> None:
    _ensure_registered()
    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None

    params = {"template": "You are {role}. User said: {user_message}"}
    inputs = {"data": {"role": "agent", "user_message": "Hello"}}

    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)

    system_prompt = outputs["system_prompt"]
    user_message = outputs["user_message"]
    assert isinstance(system_prompt, str)
    assert isinstance(user_message, str)
    assert "agent" in system_prompt
    assert "Hello" in system_prompt
    assert user_message == "Hello"


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
    inputs = {
        "data": {
            "user_message": "Hi",
            "graph_summary": {"units": [{"id": "a"}]},
        }
    }

    outputs, _ = spec.step_fn(params, inputs, {}, 0.0)
    system_prompt = outputs["system_prompt"]
    assert isinstance(system_prompt, str)
    assert "units" in system_prompt
    assert '"id": "a"' in system_prompt or "\"id\":'a'" in system_prompt


# ---- Merge → Prompt integration ----


def test_merge_then_prompt_user_message_flows() -> None:
    """Merge aggregates; Prompt receives and forwards user_message."""
    _ensure_registered()
    merge_spec = get_unit_spec("Aggregate")
    prompt_spec = get_unit_spec("Prompt")
    assert merge_spec and merge_spec.step_fn and prompt_spec and prompt_spec.step_fn

    merge_params = {"num_inputs": 2, "keys": ["user_message", "graph_summary"]}
    merge_inputs = {"in_0": "Add a valve", "in_1": "summary"}
    merge_out, _ = merge_spec.step_fn(merge_params, merge_inputs, {}, 0.0)

    merged_data = merge_out["data"]
    assert isinstance(merged_data, dict)

    prompt_params = {"template": "Graph: {graph_summary}"}
    prompt_inputs = {"data": merged_data}
    prompt_out, _ = prompt_spec.step_fn(prompt_params, prompt_inputs, {}, 0.0)

    user_message = prompt_out["user_message"]
    system_prompt = prompt_out["system_prompt"]
    assert isinstance(user_message, str)
    assert isinstance(system_prompt, str)
    assert user_message == "Add a valve"
    assert "summary" in system_prompt


def test_merge_then_prompt_empty_user_message_becomes_placeholder() -> None:
    """Merge keeps empty ``user_message``; Prompt applies ``(No message provided.)`` for the LLM."""
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
    system_prompt = outputs["system_prompt"]
    user_message = outputs["user_message"]
    assert isinstance(system_prompt, str)
    assert isinstance(user_message, str)

    assert "Workflow Designer" in system_prompt
    assert "Last action: none." in system_prompt
    assert "Add a valve" in system_prompt
    assert '{"units"' in system_prompt or "units" in system_prompt
    assert user_message == "Add a valve"


def test_prompt_workflow_designer_template_produces_full_prompt() -> None:
    """Load real workflow_designer.json; merged data produces full prompts for the LLM."""
    _ensure_registered()
    template_path = REPO_ROOT / "config" / "prompts" / "workflow_designer.json"
    if not template_path.is_file():
        return  # skip if template is not in the repo

    spec = get_unit_spec("Prompt")
    assert spec is not None and spec.step_fn is not None

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
    assert isinstance(system_prompt, str)
    assert isinstance(user_message, str)

    # The LLM agent must receive a substantial, populated system prompt.
    assert len(system_prompt) > 200, (
        "system_prompt should be full (template + substituted data)"
    )
    assert "Workflow Designer" in system_prompt
    assert (
        "Current process graph" in system_prompt
        or "graph" in system_prompt.lower()
    )

    assert user_message == "Add a Valve unit and connect it to the tank"
    assert "user_message" in outputs


def test_merge_prompt_llm_agent_receives_full_prompt() -> None:
    """Merge (8 keys) → Prompt (workflow_designer template) → LLM inputs."""
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
    assert isinstance(merged_data, dict)
    assert merged_data["user_message"] == "I want to add a valve"

    prompt_params = {"template_path": str(template_path)}
    prompt_out, _ = prompt_spec.step_fn(
        prompt_params, {"data": merged_data}, {}, 0.0
    )

    # These are the two inputs the LLMAgent unit receives.
    system_prompt = prompt_out["system_prompt"]
    user_message = prompt_out["user_message"]
    assert isinstance(system_prompt, str)
    assert isinstance(user_message, str)

    assert len(system_prompt) > 100, "LLM agent must receive full system prompt"
    assert "Workflow Designer" in system_prompt
    assert user_message == "I want to add a valve"
    assert "system_prompt" in prompt_out and "user_message" in prompt_out


if __name__ == "__main__":
    _ensure_registered()
    # Run tests manually for simple invocation without pytest
    test_merge_pass_through_when_data_is_dict()
    test_merge_aggregates_in_ports_with_keys()
    test_merge_none_inputs_become_empty_string()
    test_merge_empty_user_message_stays_empty_string()
    test_merge_whitespace_only_user_message_passthrough()
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
