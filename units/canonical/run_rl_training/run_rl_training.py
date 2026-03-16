"""
RunRLTraining unit: run RL training from an action command.

Input: action (Any) — dict with "action": "run_rl_training", "config_path" (required),
  optional "process_config_path", "total_timesteps", "checkpoint_path".
Calls runtime.train.run_training_from_config(...). Output: result (status, message, best_model_save_path, ...), error (str).
Used by GUI or workflows to start training from an Inject → RunRLTraining pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

RUN_RL_TRAINING_INPUT_PORTS = [("action", "Any")]
RUN_RL_TRAINING_OUTPUT_PORTS = [("result", "Any"), ("error", "str")]


def _run_rl_training_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """If action is run_rl_training: run runtime.train.run_training_from_config; else no-op."""
    action = inputs.get("action") or params.get("action")
    if not isinstance(action, dict) or action.get("action") != "run_rl_training":
        return ({"result": {}, "error": None}, state)

    config_path = action.get("config_path") or action.get("config")
    if not config_path or not isinstance(config_path, str):
        return (
            {"result": {}, "error": "RunRLTraining: config_path required"},
            state,
        )
    config_path = str(config_path).strip()
    process_config_path = action.get("process_config_path") or action.get("process_config")
    if process_config_path is not None:
        process_config_path = str(process_config_path).strip() or None
    total_timesteps = action.get("total_timesteps") or action.get("timesteps")
    if total_timesteps is not None:
        try:
            total_timesteps = int(total_timesteps)
        except (TypeError, ValueError):
            total_timesteps = None
    checkpoint_path = action.get("checkpoint_path") or action.get("checkpoint")
    if checkpoint_path is not None:
        checkpoint_path = str(checkpoint_path).strip() or None

    config_path_resolved = Path(config_path).expanduser().resolve()
    if not config_path_resolved.is_file():
        return (
            {"result": {}, "error": f"RunRLTraining: config file not found {config_path_resolved}"},
            state,
        )

    try:
        from runtime.train import run_training_from_config
        from core.normalizer import load_training_config_from_file
    except ImportError as e:
        return (
            {"result": {}, "error": f"RunRLTraining: import failed ({e})"},
            state,
        )

    try:
        run_training_from_config(
            config_path=config_path_resolved,
            process_config_path=Path(process_config_path) if process_config_path else None,
            checkpoint_path=checkpoint_path,
            total_timesteps=total_timesteps,
        )
    except Exception as e:
        return (
            {
                "result": {
                    "status": "failed",
                    "message": str(e)[:500],
                    "best_model_save_path": None,
                    "final_model_save_path": None,
                },
                "error": str(e)[:500],
            },
            state,
        )

    # Load config again to return callback paths (best/final model)
    try:
        cfg = load_training_config_from_file(config_path_resolved)
        cb = cfg.callbacks
        best_path = (cb.best_model_save_path or "").rstrip("/")
        if best_path:
            best_path = f"{best_path}/best_model"  # EvalCallback saves best_model.zip
        final_path = cb.final_model_save_path or ""
    except Exception:
        best_path = None
        final_path = None

    return (
        {
            "result": {
                "status": "success",
                "message": "Training complete.",
                "best_model_save_path": best_path,
                "final_model_save_path": final_path,
            },
            "error": None,
        },
        state,
    )


def register_run_rl_training() -> None:
    """Register the RunRLTraining unit type."""
    register_unit(UnitSpec(
        type_name="RunRLTraining",
        input_ports=RUN_RL_TRAINING_INPUT_PORTS,
        output_ports=RUN_RL_TRAINING_OUTPUT_PORTS,
        step_fn=_run_rl_training_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Runs RL training from action dict (action=run_rl_training, config_path, optional process_config_path, total_timesteps, checkpoint_path). Outputs result and error.",
    ))


__all__ = [
    "register_run_rl_training",
    "RUN_RL_TRAINING_INPUT_PORTS",
    "RUN_RL_TRAINING_OUTPUT_PORTS",
]
