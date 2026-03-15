#!/usr/bin/env python3
"""Write config/prompts/workflow_designer.json and rl_coach.json (structured sections format).
Paths are taken from app settings when available (e.g. when run from GUI); otherwise use default OUT_DIR.

Run from project root with: PYTHONPATH=. python scripts/write_prompt_templates.py

Workflow Designer template placeholders (filled by merge_llm from injects; keep in sync with
assistant_workflow.json keys and workflow_designer_handler.build_assistant_workflow_initial_inputs):
  graph_summary, turn_state, recent_changes_block, last_edit_block, follow_up_context, previous_turn,
  add_environment_edit, add_code_block_edit, ai_training_integration, run_workflow,
  running_flow_line, debugging_line, coding_line.
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


def _section_content(s: dict | str) -> str:
    if isinstance(s, dict):
        return s.get("content", "") or ""
    return s if isinstance(s, str) else ""


# Markers to split workflow_designer template into readable sections (order matters)
WORKFLOW_DESIGNER_MARKERS = [
    "\n\nConversational behaviour\n",
    "\n\nReasoning\n",
    "\n\nOutput format\n",
    "\n\n{turn_state}\n",
]


def _split_template(template: str, markers: list[str], section_ids: list[str]) -> list[dict[str, str]]:
    """Split template by markers; each section gets content up to next marker; last section is the rest."""
    sections = []
    rest = template
    for i, marker in enumerate(markers):
        if marker not in rest:
            continue
        before, _, after = rest.partition(marker)
        if before.strip():
            sections.append({"id": section_ids[i], "content": before.strip()})
        rest = marker + after
    if rest.strip():
        sections.append({"id": section_ids[-1], "content": rest.strip()})
    return sections


RL_COACH_MARKERS = [
    "\n\n## Conversational behavior\n",
    "\n\n## Reward shaping (DSL actions)\n",
    "\n\n## Reward DSL\n",
    "\n\n## Other edits (goal, algorithm, hyperparameters)\n",
    "\n\n## Output format\n",
    "\n\n{training_config}\n",
]
RL_SECTION_IDS = [
    "intro", "conversational_behavior", "reward_shaping", "reward_dsl",
    "other_edits", "output_format", "dynamic",
]
WORKFLOW_DESIGNER_SECTION_IDS = [
    "role_and_intro", "conversational_behaviour", "reasoning", "output_format", "dynamic",
]


def _build_workflow_designer(w_path: Path) -> str:
    """Build and write workflow_designer.json; return status message."""
    w_path.parent.mkdir(parents=True, exist_ok=True)
    if w_path.exists():
        w_data = json.loads(w_path.read_text(encoding="utf-8"))
        raw = w_data.get("template")
        if not raw and w_data.get("sections"):
            raw = "\n\n".join(_section_content(s) for s in w_data["sections"])
        template = raw or ""
        if template:
            sections = _split_template(template, WORKFLOW_DESIGNER_MARKERS, WORKFLOW_DESIGNER_SECTION_IDS)
            workflow_obj = {"format_keys": ["graph_summary"], "sections": sections}
            if "fragments" in w_data and isinstance(w_data["fragments"], dict):
                workflow_obj["fragments"] = w_data["fragments"]
            w_path.write_text(json.dumps(workflow_obj, indent=2, ensure_ascii=False), encoding="utf-8")
            return f"Wrote {w_path.name} with sections: {[s['id'] for s in sections]}"
        # fallback bootstrap
    from assistants.prompts import WORKFLOW_DESIGNER_SYSTEM  # noqa: PLC0415
    workflow_obj = {
        "format_keys": ["graph_summary"],
        "sections": [{"id": "full", "content": WORKFLOW_DESIGNER_SYSTEM + "\n\n{turn_state}\n\n{recent_changes_block}\n\nCurrent process graph (summary):\n{graph_summary}\n\n{units_library}\n\n{rag_context}\n\n{last_edit_block}\n\n{follow_up_context}\n\nPrevious turn (for context):\n{previous_turn}"}],
    }
    w_path.write_text(json.dumps(workflow_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Wrote {w_path.name} (bootstrap)"


def _build_rl_coach(r_path: Path) -> str:
    """Build and write rl_coach.json; return status message."""
    r_path.parent.mkdir(parents=True, exist_ok=True)
    if r_path.exists():
        r_data = json.loads(r_path.read_text(encoding="utf-8"))
        raw = r_data.get("template")
        if not raw and r_data.get("sections"):
            raw = "\n\n".join(_section_content(s) for s in r_data["sections"])
        template = raw or ""
        if template:
            sections = _split_template(template, RL_COACH_MARKERS, RL_SECTION_IDS)
            if not sections:
                sections = [{"id": "full", "content": template}]
            rl_obj = {"format_keys": ["training_config"], "sections": sections}
            r_path.write_text(json.dumps(rl_obj, indent=2, ensure_ascii=False), encoding="utf-8")
            return f"Wrote {r_path.name} with sections: {[s['id'] for s in sections]}"
    from assistants.prompts import RL_COACH_SYSTEM  # noqa: PLC0415
    rl_obj = {"format_keys": ["training_config"], "sections": [{"id": "full", "content": RL_COACH_SYSTEM + "\n\n{training_config}\n\n{rag_context}"}]}
    r_path.write_text(json.dumps(rl_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Wrote {r_path.name} (bootstrap)"


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
