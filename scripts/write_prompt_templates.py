#!/usr/bin/env python3
"""Write config/prompts/workflow_designer.json and rl_coach.json (structured sections format)."""
import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Workflow Designer: load current and convert to sections (or bootstrap)
    w_path = OUT_DIR / "workflow_designer.json"
    if w_path.exists():
        w_data = json.loads(w_path.read_text(encoding="utf-8"))
        raw = w_data.get("template")
        if not raw and w_data.get("sections"):
            raw = "\n\n".join(_section_content(s) for s in w_data["sections"])
        template = raw or ""
        if template:
            section_ids = ["role_and_intro", "conversational_behaviour", "reasoning", "output_format", "dynamic"]
            sections = _split_template(template, WORKFLOW_DESIGNER_MARKERS, section_ids)
            workflow_obj = {"format_keys": ["graph_summary"], "sections": sections}
            if "fragments" in w_data and isinstance(w_data["fragments"], dict):
                workflow_obj["fragments"] = w_data["fragments"]
            w_path.write_text(json.dumps(workflow_obj, indent=2, ensure_ascii=False), encoding="utf-8")
            print("Wrote workflow_designer.json with sections:", [s["id"] for s in sections])
        else:
            from assistants.prompts import WORKFLOW_DESIGNER_SYSTEM  # noqa: PLC0415
            workflow_obj = {
                "format_keys": ["graph_summary"],
                "sections": [{"id": "full", "content": WORKFLOW_DESIGNER_SYSTEM + "\n\n{turn_state}\n\n{recent_changes_block}\n\nCurrent process graph (summary):\n{graph_summary}\n\n{units_library}\n\n{rag_context}\n\n{last_edit_block}"}],
            }
            w_path.write_text(json.dumps(workflow_obj, indent=2, ensure_ascii=False), encoding="utf-8")
            print("Wrote workflow_designer.json (bootstrap)")
    else:
        from assistants.prompts import WORKFLOW_DESIGNER_SYSTEM  # noqa: PLC0415
        workflow_obj = {
            "format_keys": ["graph_summary"],
            "sections": [{"id": "full", "content": WORKFLOW_DESIGNER_SYSTEM + "\n\n{turn_state}\n\n{recent_changes_block}\n\nCurrent process graph (summary):\n{graph_summary}\n\n{units_library}\n\n{rag_context}\n\n{last_edit_block}"}],
        }
        w_path.write_text(json.dumps(workflow_obj, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Wrote workflow_designer.json (bootstrap)")

    # RL Coach: load current and convert to sections (or bootstrap)
    RL_COACH_MARKERS = [
        "\n\n## Conversational behavior\n",
        "\n\n## Reward shaping (DSL actions)\n",
        "\n\n## Reward DSL\n",
        "\n\n## Other edits (goal, algorithm, hyperparameters)\n",
        "\n\n## Output format\n",
        "\n\n{training_config}\n",
    ]
    rl_section_ids = ["intro", "conversational_behavior", "reward_shaping", "reward_dsl", "other_edits", "output_format", "dynamic"]
    r_path = OUT_DIR / "rl_coach.json"
    if r_path.exists():
        r_data = json.loads(r_path.read_text(encoding="utf-8"))
        raw = r_data.get("template")
        if not raw and r_data.get("sections"):
            raw = "\n\n".join(_section_content(s) for s in r_data["sections"])
        template = raw or ""
        if template:
            sections = _split_template(template, RL_COACH_MARKERS, rl_section_ids)
            if not sections:
                sections = [{"id": "full", "content": template}]
            rl_obj = {"format_keys": ["training_config"], "sections": sections}
            r_path.write_text(json.dumps(rl_obj, indent=2, ensure_ascii=False), encoding="utf-8")
            print("Wrote rl_coach.json with sections:", [s["id"] for s in sections])
        else:
            from assistants.prompts import RL_COACH_SYSTEM  # noqa: PLC0415
            rl_obj = {"format_keys": ["training_config"], "sections": [{"id": "full", "content": RL_COACH_SYSTEM + "\n\n{training_config}\n\n{rag_context}"}]}
            r_path.write_text(json.dumps(rl_obj, indent=2, ensure_ascii=False), encoding="utf-8")
            print("Wrote rl_coach.json (bootstrap)")
    else:
        from assistants.prompts import RL_COACH_SYSTEM  # noqa: PLC0415
        rl_obj = {"format_keys": ["training_config"], "sections": [{"id": "full", "content": RL_COACH_SYSTEM + "\n\n{training_config}\n\n{rag_context}"}]}
        r_path.write_text(json.dumps(rl_obj, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Wrote rl_coach.json (bootstrap)")


if __name__ == "__main__":
    main()
