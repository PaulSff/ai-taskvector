"""
ApplyTrainingConfigEdits unit: applies parsed training-config edits to the current config.

Inputs: training_config (current config dict or TrainingConfig), edits (list from TrainingConfigParser).
Outputs: result (kind, content_for_display, config), status (attempted, success, error), config (updated dict for saving), error (str).
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from core.gym.training_edits import apply_config_edits
from units.canonical.delegate_request.delegate_request import delegate_handoff_data_from_payload
from core.normalizer import to_training_config

APPLY_TRAINING_CONFIG_EDITS_INPUT_PORTS = [("training_config", "Any"), ("edits", "Any")]
APPLY_TRAINING_CONFIG_EDITS_OUTPUT_PORTS = [("result", "Any"), ("status", "Any"), ("config", "Any"), ("error", "str")]


def _edits_summary(edits: list[dict[str, Any]]) -> str:
    """Short summary of edits for status."""
    parts: list[str] = []
    for e in edits:
        if not isinstance(e, dict):
            continue
        if e.get("action") == "no_edit":
            continue
        action = e.get("action")
        if action:
            parts.append(str(action))
        elif "goal" in e:
            parts.append("goal")
        elif "rewards" in e:
            parts.append("rewards")
        elif "hyperparameters" in e:
            parts.append("hyperparameters")
        elif "callbacks" in e:
            parts.append("callbacks")
        else:
            parts.append("config")
    return "; ".join(parts)[:200] if parts else ""


def _apply_training_config_edits_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply edits to training config; return result, status, and updated config."""
    config_in = inputs.get("training_config")
    edits_raw = inputs.get("edits")

    current: dict[str, Any] = {}
    if config_in is not None:
        if hasattr(config_in, "model_dump"):
            current = config_in.model_dump(by_alias=True)
        elif isinstance(config_in, dict):
            current = dict(config_in)

    edits: list[dict[str, Any]] = []
    if isinstance(edits_raw, list):
        edits = [e for e in edits_raw if isinstance(e, dict)]
    elif isinstance(edits_raw, dict) and "edits" in edits_raw:
        edits = list(edits_raw.get("edits") or [])
        if not isinstance(edits, list):
            edits = []

    delegate_payloads = [e for e in edits if isinstance(e, dict) and e.get("action") == "delegate_request"]
    training_edits = [e for e in edits if not (isinstance(e, dict) and e.get("action") == "delegate_request")]
    delegate_handoff: dict[str, Any] | None = None
    if delegate_payloads:
        delegate_handoff = delegate_handoff_data_from_payload(delegate_payloads[0])

    apply_result: dict[str, Any] = {"attempted": False, "success": None, "error": None}
    result: dict[str, Any] = {
        "kind": "no_edits",
        "content_for_display": "",
        "config": current,
        "edits": edits,
        "delegate_handoff": delegate_handoff,
    }

    if not training_edits:
        return (
            {"result": result, "status": apply_result, "config": current, "error": None},
            state,
        )

    apply_result["attempted"] = True
    try:
        merged = apply_config_edits(current, training_edits)
        canonical = to_training_config(merged, format="dict")
        out_dict = canonical.model_dump(by_alias=True)
        apply_result["success"] = True
        result["kind"] = "applied"
        result["config"] = out_dict
        summary = _edits_summary(training_edits)
        if summary:
            apply_result["edits_summary"] = summary
        result["content_for_display"] = summary or "Config updated."
        return (
            {"result": result, "status": apply_result, "config": out_dict, "error": None},
            state,
        )
    except Exception as e:
        apply_result["success"] = False
        err_str = str(e)
        apply_result["error"] = err_str
        result["kind"] = "apply_failed"
        return (
            {"result": result, "status": apply_result, "config": current, "error": err_str},
            state,
        )


def register_apply_training_config_edits() -> None:
    """Register the ApplyTrainingConfigEdits unit type."""
    register_unit(UnitSpec(
        type_name="ApplyTrainingConfigEdits",
        input_ports=APPLY_TRAINING_CONFIG_EDITS_INPUT_PORTS,
        output_ports=APPLY_TRAINING_CONFIG_EDITS_OUTPUT_PORTS,
        step_fn=_apply_training_config_edits_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Applies parsed training-config edits; outputs result, status, and updated config dict.",
    ))


__all__ = [
    "register_apply_training_config_edits",
    "APPLY_TRAINING_CONFIG_EDITS_INPUT_PORTS",
    "APPLY_TRAINING_CONFIG_EDITS_OUTPUT_PORTS",
]
