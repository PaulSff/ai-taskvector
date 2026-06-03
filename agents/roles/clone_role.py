#!/usr/bin/env python3
"""
Scaffold a new role by cloning the analyst role and updating files.
Usage:
  python clone_role.py --new-role administrator \
    --responsibility "Responsible for X" \
    --intro "Hello, I'm Admin." \
    --tools grep read_file formulas_calc
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from agents.roles import roles_definitions_dir

# -- Config: source role ids / locations
SRC_ROLE = "analyst"
_ROLES_DIR = roles_definitions_dir()
SRC_ROLE_DIR = _ROLES_DIR / SRC_ROLE
_REPO_ROOT = _ROLES_DIR.parent.parent
SRC_ROLE_TURNS = _REPO_ROOT / "gui" / "chat" / "role_turns" / SRC_ROLE
TOOLS_CATALOG = _REPO_ROOT / "agents" / "tools" / "catalog.py"


# -- Helpers
def ensure_exists(p: Path, what: str):
    if not p.exists():
        print(f"ERROR: {what} not found: {p}", file=sys.stderr)
        sys.exit(1)


def copy_tree(src: Path, dst: Path):
    if dst.exists():
        print(f"ERROR: destination exists: {dst}", file=sys.stderr)
        sys.exit(1)
    shutil.copytree(src, dst)
    print(f"Copied {src} -> {dst}")


def replace_in_file(path: Path, replacements: dict):
    s = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        s = s.replace(old, new)
    path.write_text(s, encoding="utf-8")
    print(f"Updated {path}")


def regex_replace_in_file(path: Path, pattern, repl):
    s = path.read_text(encoding="utf-8")
    s2 = re.sub(pattern, repl, s, flags=re.MULTILINE)
    if s2 != s:
        path.write_text(s2, encoding="utf-8")
        print(f"Regex-updated {path}")


# -- Main operations
def main(args):
    new_id = args.new_role.strip()
    if not re.match(r"^[a-z0-9_]+$", new_id):
        print(
            "ERROR: new_role must be lowercase with letters/numbers/underscores",
            file=sys.stderr,
        )
        sys.exit(1)

    new_role_dir = Path("agents/roles") / new_id
    new_role_turns = Path("gui/chat/role_turns") / new_id

    # 1. Sanity checks
    ensure_exists(SRC_ROLE_DIR, "source role folder")
    ensure_exists(SRC_ROLE_TURNS, "source role_turns folder")

    # 1. Clone role package
    copy_tree(SRC_ROLE_DIR, new_role_dir)

    # 2. Rename workflow JSON file in role folder
    # find any file matching analyst*_workflow.json
    for p in new_role_dir.glob("*workflow.json"):
        old_name = p.name
        new_name = old_name.replace(SRC_ROLE, new_id)
        p.rename(new_role_dir / new_name)
        print(f"Renamed workflow file {old_name} -> {new_name}")

    # 3. Update prompts.py constants and sections
    prompts_py = new_role_dir / "prompts.py"
    if prompts_py.exists():
        # 3a. Rename constants: all-uppercase tokens containing ANALYST -> NEWID upper
        old_token = "ANALYST"
        new_token = new_id.upper()
        # naive replace of identifiers
        replace_in_file(prompts_py, {old_token: new_token})
        # 3b. Replace sections if provided
        new_sections = {}
        if args.introduction_words:
            new_sections[f"{new_token}_SECTION_ROLE_AND_INTRO_BODY"] = (
                args.introduction_words
            )
        if args.responsibility_description:
            # not a prompts section but keep in case user wants mapping
            pass
        if args.tools:
            # insert tool lines after a line containing "Extra actions:"
            s = prompts_py.read_text(encoding="utf-8")
            marker = "Extra actions:"
            if marker in s:
                insert_idx = s.index(marker) + len(marker)
                tool_lines = (
                    "\n" + "\n".join(f"{{tool:{t}}}" for t in args.tools) + "\n"
                )
                s = s[:insert_idx] + tool_lines + s[insert_idx:]
                prompts_py.write_text(s, encoding="utf-8")
                print(f"Inserted tools into {prompts_py}")
    else:
        print(f"Warning: {prompts_py} not found, skipping prompts update")

    # 4. role.yaml updates
    role_yaml = new_role_dir / "role.yaml"
    ensure_exists(role_yaml, "role.yaml")
    s = role_yaml.read_text(encoding="utf-8")
    # id must equal folder name
    s = re.sub(r"^id:\s*.+$", f"id: {new_id}", s, flags=re.MULTILINE)
    if args.responsibility_description:
        if "responsibility_description:" in s:
            s = re.sub(
                r"responsibility_description:\s*\|?[\s\S]*?(?:\n(?=[A-Za-z_]+:)|\n$)",
                f"responsibility_description: |\n  {args.responsibility_description}\n",
                s,
            )
        else:
            # append
            s += f"\nresponsibility_description: |\n  {args.responsibility_description}\n"
    if args.introduction_words:
        if "introduction_words:" in s:
            s = re.sub(
                r"introduction_words:\s*\|?[\s\S]*?(?:\n(?=[A-Za-z_]+:)|\n$)",
                f"introduction_words: |\n  {args.introduction_words}\n",
                s,
            )
        else:
            s += f"\nintroduction_words: |\n  {args.introduction_words}\n"
    if args.tools:
        # replace tools: block with provided ordered tools
        tools_block = "tools:\n" + "\n".join(f"- {t}" for t in args.tools) + "\n"
        if re.search(r"^tools:\s*\n(?:- .+\n)*", s, flags=re.MULTILINE):
            s = re.sub(r"^tools:\s*\n(?:- .+\n)*", tools_block, s, flags=re.MULTILINE)
        else:
            s += "\n" + tools_block
    role_yaml.write_text(s, encoding="utf-8")
    print(f"Updated {role_yaml}")

    # 5. Update workflow json content (template_path + role.* keys)
    # find workflow json in new role dir
    for p in new_role_dir.glob(f"*{SRC_ROLE}workflow.json"):
        j = json.loads(p.read_text(encoding="utf-8"))
        j_s = json.dumps(j)
        # replace template path analyst.json -> new_id.json
        j_s = j_s.replace(
            "config/prompts/analyst.json", f"config/prompts/{new_id}.json"
        )
        # replace role.analyst -> role.<new_id>
        j_s = j_s.replace("role.analyst.", f"role.{new_id}.")
        p.write_text(j_s, encoding="utf-8")
        print(f"Patched workflow json: {p.name}")

    # 6. Clone gui/chat/role_turns package
    copy_tree(SRC_ROLE_TURNS, new_role_turns)

    # 7. Update handler.py and __init__.py replacements
    handler_py = new_role_turns / "handler.py"
    init_py = new_role_turns / "__init__.py"
    ensure_exists(handler_py, "handler.py in new role_turns")
    ensure_exists(init_py, "__init__.py in new role_turns")

    # Replace constants and tokens in handler.py
    old_upper = SRC_ROLE.upper()
    new_upper = new_id.upper()
    replacements = {
        f"{old_upper}_ROLE_ID": f"{new_upper}_ROLE_ID",
        f"ORDERED_{old_upper}_TOOLS": f"ORDERED_{new_upper}_TOOLS",
        f"{SRC_ROLE}_workflow.json": f"{new_id}_workflow.json",
        "config/prompts/analyst.json": f"config/prompts/{new_id}.json",
        "AnalystChatHandler": f"{new_id.capitalize()}ChatHandler",
        "analyst_mode": f"{new_id}_mode",
    }
    # generic role.analyst -> role.<new_id>
    # and role_analyst -> role_<new_id>
    replace_in_file(handler_py, replacements)
    replace_in_file(
        init_py,
        {
            "Analyst chat turn: analysis-focused tools, comments/todos only (no structural graph edits).": f"{new_id.capitalize()} chat turn: {new_id}-focused tools, comments/todos only (no structural graph edits).",
            "from .handler import AnalystChatHandler": f"from .handler import {new_id.capitalize()}ChatHandler",
            '__all__ = ["AnalystChatHandler"]': f'__all__ = ["{new_id.capitalize()}ChatHandler"]',
        },
    )

    # update other identifier occurrences in handler.py (ANALYST -> NEW)
    regex_replace_in_file(handler_py, r"\bANALYST\b", new_upper)
    regex_replace_in_file(handler_py, r"\banalyst\b", new_id)

    # 8. Update agents/tools/catalog.py: add ordered tools and helper
    if TOOLS_CATALOG.exists():
        s = TOOLS_CATALOG.read_text(encoding="utf-8")
        marker = f"ORDERED_{SRC_ROLE.upper()}_TOOLS"
        if marker in s:
            # extract the existing tuple block for analyst tools
            m = re.search(rf"(#.*?{re.escape(marker)}.*?=\s*\([^\)]*\))", s, flags=re.S)
            if m:
                block = m.group(1)
                new_block = block.replace(marker, f"ORDERED_{new_upper}_TOOLS")
                # adjust comment line
                new_block = new_block.replace(
                    f"# {SRC_ROLE.capitalize()} chat:", f"# {new_id} chat:"
                )
                # insert helper function after the block
                helper = f'\n\ndef {new_id}_tool_ids() -> tuple[str, ...]:\n    """Ordered tool ids for ``agents/roles/{new_id}/role.yaml`` ``tools``."""\n    return tuple(tid for tid, _ in ORDERED_{new_upper}_TOOLS)\n'
                s = s.replace(block, block + "\n\n" + new_block + helper)
                TOOLS_CATALOG.write_text(s, encoding="utf-8")
                print(
                    f"Appended ORDERED_{new_upper}_TOOLS and helper to {TOOLS_CATALOG}"
                )
            else:
                print(
                    f"Warning: couldn't find analyst ORDERED block pattern in {TOOLS_CATALOG}, skipping tools insertion"
                )
        else:
            print(
                f"Warning: marker {marker} not found in {TOOLS_CATALOG}, skipping tools insertion"
            )
    else:
        print(f"Warning: tools catalog not found: {TOOLS_CATALOG}")

    print(
        "Done. Please review the created files and run any project-specific prompt template writer script if needed."
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--new-role", required=True, help="new role id (lowercase, underscored)"
    )
    ap.add_argument("--responsibility", dest="responsibility_description", default=None)
    ap.add_argument("--intro", dest="introduction_words", default=None)
    ap.add_argument("--tools", nargs="*", default=[])
    args = ap.parse_args()
    main(args)
