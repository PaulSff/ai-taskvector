"""
System prompts and fragment constants for assistants.

**Layout (Phase 4):** Role-specific default strings live under ``assistants/roles/<role_id>/prompts.py``
(workflow_designer, rl_coach, chat_name_creator). This module re-exports them so existing
``from assistants.prompts import WORKFLOW_DESIGNER_*`` imports stay stable.

**Shared machinery here:** ``get_fragment``, JSON template loading, and optional **fragment overrides**
from ``config/prompts/workflow_designer.json`` (keys under ``fragments``) applied after import.
Workflow Designer role keys are applied in ``assistants/roles/workflow_designer/prompts.py`` via
``apply_workflow_designer_role_fragments``; tool follow-up strings are patched on per-skill ``follow_ups``
modules via ``apply_workflow_designer_json_skill_fragments`` (``assistants/skills/follow_up_fragment_overrides.py``).

**Workflow Designer:** Main system prompt template is ``config/prompts/workflow_designer.json``;
defaults for fragments and ``WORKFLOW_DESIGNER_SYSTEM`` / ``WORKFLOW_DESIGNER_DYNAMIC_SECTION`` come from
``assistants/roles/workflow_designer/prompts.py``. Run **Build prompts** to refresh JSON.

**RL Coach:** ``config/prompts/rl_coach.json``; source strings in ``assistants/roles/rl_coach/prompts.py``.

**Create filename:** ``assistants/roles/chat_name_creator/prompts.py``.

**scripts/write_prompt_templates.py** still imports from ``assistants.prompts`` (unchanged entry point).

**core/graph/graph_edits.py:** Imports error strings (WORKFLOW_DESIGNER_ADD_PIPELINE_*_ERROR, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _section_content(item: object) -> str:
    """Extract content from a section: string or dict with 'content' key."""
    if isinstance(item, dict) and "content" in item:
        c = item["content"]
        return c if isinstance(c, str) else ""
    return item if isinstance(item, str) else ""


def _load_template_from_json(name: str) -> str:
    """Load template string from config/prompts/<name>.json ('template' or assembled from 'sections')."""
    path = _PROMPTS_DIR / name
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ""
        template = data.get("template")
        if isinstance(template, str) and template.strip():
            return template
        sections = data.get("sections")
        if isinstance(sections, list) and sections:
            return "\n\n".join(_section_content(s).strip() for s in sections if _section_content(s).strip())
        return ""
    except (OSError, json.JSONDecodeError, TypeError):
        return ""


def _load_fragments(name: str) -> dict[str, str]:
    """Load fragments dict from config/prompts/<name>.json (key 'fragments'). Used for self-correction, errors, follow-ups."""
    path = _PROMPTS_DIR / (name if name.endswith(".json") else name + ".json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        frag = data.get("fragments")
        return frag if isinstance(frag, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def get_fragment(template_name: str, fragment_key: str, **kwargs: str) -> str:
    """Load a fragment from template JSON and substitute placeholders (e.g. error=..., runtime=..., unit_type=...). For use in Merge → Prompt pipeline."""
    fragments = _load_fragments(template_name)
    template = fragments.get(fragment_key, "")
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


# Re-export role prompt constants (stable import path for the rest of the codebase).
from assistants.roles.chat_name_creator.prompts import *  # noqa: F403,E402
from assistants.roles.rl_coach.prompts import *  # noqa: F403,E402
from assistants.roles.workflow_designer.prompts import *  # noqa: F403,E402
from assistants.skills.follow_up_fragment_overrides import apply_workflow_designer_json_skill_fragments

# Optional override: workflow_designer.json "fragments" (if present). Defaults live in the role module, not JSON.
_WF_FRAGMENTS = _load_fragments("workflow_designer.json")
apply_workflow_designer_role_fragments(_WF_FRAGMENTS)
apply_workflow_designer_json_skill_fragments(_WF_FRAGMENTS)
