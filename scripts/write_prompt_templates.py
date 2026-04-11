#!/usr/bin/env python3
"""Write config/prompts/workflow_designer.json and rl_coach.json (structured sections format).
Paths are taken from app settings when available (e.g. when run from GUI); otherwise use default OUT_DIR.

Run from project root with: PYTHONPATH=. python scripts/write_prompt_templates.py

Workflow Designer template placeholders (filled by merge_llm from injects; keep in sync with
assistant_workflow.json keys and assistants.roles.workflow_designer.workflow_inputs.build_assistant_workflow_initial_inputs):
  graph_summary, language, session_language, turn_state, recent_changes_block, last_edit_block, follow_up_context,
  previous_turn, units_library, rag_context, add_environment_edit, add_code_block_edit,
  ai_training_integration, run_workflow, running_flow_line, debugging_line, coding_line.

Per-tool "Extra actions" lines are resolved at import from ``assistants/tools/<tool_id>/prompt.py`` via
``{tool:tool_id}`` in ``_WORKFLOW_DESIGNER_SYSTEM_RAW`` (see ``assistants.tools.prompt_lines``); the written JSON
contains the expanded text.

**Build prompts / GUI "Build prompts"** reads constants from ``assistants.prompts`` (re-exports from
``assistants/roles/<role_id>/prompts.py``) and writes JSON: workflow_designer uses
WORKFLOW_DESIGNER_SYSTEM + WORKFLOW_DESIGNER_DYNAMIC_SECTION; rl_coach uses RL_COACH_SYSTEM +
RL_COACH_DYNAMIC_SECTION; create_filename uses CREATE_FILENAME_SYSTEM. Edit the role ``prompts.py``
files (or JSON ``fragments`` overrides), then run Build prompts.
"""
import json
from pathlib import Path
from typing import Tuple

OUT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _resolve_output_paths(
    workflow_designer_path: Path | None,
    rl_coach_path: Path | None,
) -> Tuple[Path, Path]:
    """Resolve paths from app settings when None; otherwise use OUT_DIR defaults."""
    if workflow_designer_path is not None and rl_coach_path is not None:
        return workflow_designer_path, rl_coach_path
    try:
        from gui.flet.components.settings import (
            get_workflow_designer_prompt_path,
            get_rl_coach_prompt_path,
        )
        w = get_workflow_designer_prompt_path() if workflow_designer_path is None else workflow_designer_path
        r = get_rl_coach_prompt_path() if rl_coach_path is None else rl_coach_path
        return w, r
    except Exception:
        pass
    w = workflow_designer_path or (OUT_DIR / "workflow_designer.json")
    r = rl_coach_path or (OUT_DIR / "rl_coach.json")
    return w, r


def _resolve_create_filename_path(create_filename_path: Path | None) -> Path:
    """Resolve create_filename prompt path from app settings when None."""
    if create_filename_path is not None:
        return create_filename_path
    try:
        from gui.flet.components.settings import get_create_filename_prompt_path
        return get_create_filename_prompt_path()
    except Exception:
        pass
    return OUT_DIR / "create_filename.json"


# Boundaries inside WORKFLOW_DESIGNER_SYSTEM (assistants/roles/workflow_designer/prompts.py; must match that string).
_WD_M1 = "\n\nConversational behaviour\n"
_WD_M2 = "\n\nReasoning\n"
_WD_M3 = "\n\nOutput format\n"


def _sections_from_workflow_designer_prompts() -> list[dict[str, str]]:
    """
    Split WORKFLOW_DESIGNER_SYSTEM into role/conversational/reasoning/output_format and append
    WORKFLOW_DESIGNER_DYNAMIC_SECTION. Source: assistants/roles/workflow_designer/prompts.py (via assistants.prompts).
    """
    from assistants.prompts import (  # noqa: PLC0415
        WORKFLOW_DESIGNER_DYNAMIC_SECTION,
        WORKFLOW_DESIGNER_SYSTEM,
    )

    s = WORKFLOW_DESIGNER_SYSTEM.strip()
    i1, i2, i3 = s.find(_WD_M1), s.find(_WD_M2), s.find(_WD_M3)
    if i1 < 0 or i2 < 0 or i3 < 0 or not (i1 < i2 < i3):
        raise ValueError(
            "WORKFLOW_DESIGNER_SYSTEM is missing expected section markers "
            f"({_WD_M1!r}, {_WD_M2!r}, {_WD_M3!r}). Update workflow_designer/prompts.py or _WD_M* in write_prompt_templates.py."
        )
    return [
        {"id": "role_and_intro", "content": s[:i1].strip()},
        {"id": "conversational_behaviour", "content": s[i1:i2].strip()},
        {"id": "reasoning", "content": s[i2:i3].strip()},
        {"id": "output_format", "content": s[i3:].strip()},
        {"id": "dynamic", "content": WORKFLOW_DESIGNER_DYNAMIC_SECTION.strip()},
    ]


# Boundaries inside RL_COACH_SYSTEM (assistants/roles/rl_coach/prompts.py; must match that string).
_RL_M1 = "\n\n## Conversational behavior\n"
_RL_M2 = "\n\n## Reward shaping (DSL actions)\n"
_RL_M3 = "\n\n## Reward DSL\n"
_RL_M4 = "\n\n## Other edits (goal, algorithm, hyperparameters)\n"
_RL_M5 = "\n\n## Output format\n"


def _sections_from_rl_coach_prompts() -> list[dict[str, str]]:
    """
    Split RL_COACH_SYSTEM into intro + markdown sections and append RL_COACH_DYNAMIC_SECTION.
    Source: assistants/roles/rl_coach/prompts.py (via assistants.prompts).
    """
    from assistants.prompts import (  # noqa: PLC0415
        RL_COACH_DYNAMIC_SECTION,
        RL_COACH_SYSTEM,
    )

    s = RL_COACH_SYSTEM.strip()
    i1, i2, i3, i4, i5 = s.find(_RL_M1), s.find(_RL_M2), s.find(_RL_M3), s.find(_RL_M4), s.find(_RL_M5)
    if i1 < 0 or i2 < 0 or i3 < 0 or i4 < 0 or i5 < 0 or not (i1 < i2 < i3 < i4 < i5):
        raise ValueError(
            "RL_COACH_SYSTEM is missing expected section markers "
            f"({_RL_M1!r}, {_RL_M2!r}, {_RL_M3!r}, {_RL_M4!r}, {_RL_M5!r}). "
            "Update rl_coach/prompts.py or _RL_M* in write_prompt_templates.py."
        )
    return [
        {"id": "intro", "content": s[:i1].strip()},
        {"id": "conversational_behavior", "content": s[i1:i2].strip()},
        {"id": "reward_shaping", "content": s[i2:i3].strip()},
        {"id": "reward_dsl", "content": s[i3:i4].strip()},
        {"id": "other_edits", "content": s[i4:i5].strip()},
        {"id": "output_format", "content": s[i5:].strip()},
        {"id": "dynamic", "content": RL_COACH_DYNAMIC_SECTION.strip()},
    ]


def _build_workflow_designer(w_path: Path) -> str:
    """Build and write workflow_designer.json from role prompts (via assistants.prompts); return status message."""
    w_path.parent.mkdir(parents=True, exist_ok=True)
    fragments: dict | None = None
    if w_path.exists():
        try:
            w_data = json.loads(w_path.read_text(encoding="utf-8"))
            if isinstance(w_data.get("fragments"), dict):
                fragments = w_data["fragments"]
        except (OSError, json.JSONDecodeError):
            pass

    sections = _sections_from_workflow_designer_prompts()
    workflow_obj: dict = {"format_keys": ["graph_summary"], "sections": sections}
    if fragments is not None:
        workflow_obj["fragments"] = fragments
    w_path.write_text(json.dumps(workflow_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Wrote {w_path.name} from workflow_designer role prompts with sections: {[s['id'] for s in sections]}"


def _build_rl_coach(r_path: Path) -> str:
    """Build and write rl_coach.json from role prompts (via assistants.prompts); return status message."""
    r_path.parent.mkdir(parents=True, exist_ok=True)
    sections = _sections_from_rl_coach_prompts()
    rl_obj: dict = {
        "format_keys": ["training_config", "training_results", "rag_context", "previous_turn"],
        "sections": sections,
    }
    r_path.write_text(json.dumps(rl_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Wrote {r_path.name} from rl_coach role prompts with sections: {[s['id'] for s in sections]}"


def _build_create_filename(c_path: Path) -> str:
    """Build and write create_filename.json; return status message."""
    c_path.parent.mkdir(parents=True, exist_ok=True)
    from assistants.prompts import CREATE_FILENAME_SYSTEM  # noqa: PLC0415
    create_obj = {"sections": [{"id": "full", "content": CREATE_FILENAME_SYSTEM}]}
    c_path.write_text(json.dumps(create_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Wrote {c_path.name}"


def build_prompt_templates(
    workflow_designer_path: Path | None = None,
    rl_coach_path: Path | None = None,
    create_filename_path: Path | None = None,
) -> Tuple[bool, str]:
    """
    Build workflow_designer.json, rl_coach.json, and create_filename.json at the given paths.
    If a path is None, it is resolved from app settings (when available), else OUT_DIR.
    Returns (success, message).
    """
    try:
        w_path, r_path = _resolve_output_paths(workflow_designer_path, rl_coach_path)
        c_path = _resolve_create_filename_path(create_filename_path)
        msg1 = _build_workflow_designer(w_path)
        msg2 = _build_rl_coach(r_path)
        msg3 = _build_create_filename(c_path)
        return True, f"{msg1}. {msg2}. {msg3}"
    except Exception as e:
        return False, str(e)


def main() -> None:
    """CLI entry: use paths from app settings or OUT_DIR."""
    success, message = build_prompt_templates(None, None)
    if success:
        print(message)
    else:
        raise SystemExit(message)


if __name__ == "__main__":
    main()
