#!/usr/bin/env python3
"""
Scaffold a new role by cloning the analyst role and updating files.
Usage:
  python agents/roles/clone_role.py --new-role administrator \
    --character-name Alex \
    --responsibility "Responsible for X" \
    --intro "Hello, I'm Admin." \
    --tools grep read_file formulas_calc
"""

from __future__ import annotations

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
ROLES_REGISTRY = _REPO_ROOT / "agents" / "roles" / "registry.py"


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


# safe YAML name replacement helper (simple best-effort)
def replace_yaml_field(content: str, field: str, value: str) -> str:
    if re.search(rf"^{re.escape(field)}:\s*.+$", content, flags=re.MULTILINE):
        content = re.sub(
            rf"^{re.escape(field)}:\s*.+$",
            f"{field}: {value}",
            content,
            flags=re.MULTILINE,
        )
    else:
        content += f"\n{field}: {value}\n"
    return content


# -- Main operations
def main(args):
    new_id = args.new_role.strip()
    character_name = args.character_name.strip()
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
    for p in new_role_dir.glob("*workflow.json"):
        old_name = p.name
        new_name = old_name.replace(SRC_ROLE, new_id)
        p.rename(new_role_dir / new_name)
        print(f"Renamed workflow file {old_name} -> {new_name}")

    # 3. Update prompts.py constants and sections
    prompts_py = new_role_dir / "prompts.py"
    if prompts_py.exists():
        old_token = "ANALYST"
        new_token = new_id.upper()
        replace_in_file(prompts_py, {old_token: new_token})

        # textual/path replacements required for new role
        replace_in_file(
            prompts_py,
            {
                "config/prompts/analyst.json": f"config/prompts/{new_id}.json",
                "agents/roles/analyst/role.yaml": f"agents/roles/{new_id}/role.yaml",
            },
        )

        # docstring and narrative text replacements (three-pattern block)
        regex_replace_in_file(
            prompts_py,
            r'"""Analyst agent prompt template',
            f'"""{new_id.capitalize()} agent prompt template',
        )
        regex_replace_in_file(
            prompts_py,
            r"Analyst omits ``read_code_block``",
            f"{new_id.capitalize()} omits ``read_code_block``",
        )
        regex_replace_in_file(
            prompts_py,
            r"The analyst chat workflow loads",
            f"The {new_id.replace('_', '-')} chat workflow loads",
        )

        # rename internal helper functions and update references
        #  - _analyst_introduction_block -> _<new_id>_introduction_block
        #  - analyst_prompt_template_dict -> <new_id>_prompt_template_dict
        regex_replace_in_file(
            prompts_py,
            r"def _analyst_introduction_block\(\)",
            f"def _{new_id}_introduction_block()",
        )
        # update the docstring line inside the function if present (keeps same formatting)
        regex_replace_in_file(
            prompts_py,
            r"Opening paragraph from ``agents\.roles\.analyst\/role\.yaml``",
            f"Opening paragraph from ``agents.roles.{new_id}/role.yaml``",
        )

        # rename the public factory function and update its internal call to the introduction helper
        regex_replace_in_file(
            prompts_py,
            r"def analyst_prompt_template_dict\(\)",
            f"def {new_id}_prompt_template_dict()",
        )
        regex_replace_in_file(
            prompts_py,
            r'role_and_intro = f"\{_analyst_introduction_block\(\)\}"',
            f'role_and_intro = f"{{_{new_id}_introduction_block()}}"',
        )
        # also replace any direct references to _analyst_introduction_block elsewhere
        regex_replace_in_file(
            prompts_py,
            r"_analyst_introduction_block\(\)",
            f"_{new_id}_introduction_block()",
        )

        # remaining canonical path and workflow comment references
        regex_replace_in_file(
            prompts_py,
            r"Canonical location: ``agents/roles/analyst/prompts\.py``",
            f"Canonical location: ``agents/roles/{new_id}/prompts.py``",
        )
        regex_replace_in_file(
            prompts_py,
            r"# Section ids must stay aligned with ``analyst_workflow\.json``",
            f"# Section ids must stay aligned with ``{new_id}_workflow.json``",
        )

        # insert tools after marker if requested (unchanged)
        if args.tools:
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

    # 4. role.yaml updates (id, role_name, name, responsibility, intro, tools)
    role_yaml = new_role_dir / "role.yaml"
    ensure_exists(role_yaml, "role.yaml")
    s = role_yaml.read_text(encoding="utf-8")
    # id must equal folder name
    s = re.sub(r"^id:\s*.+$", f"id: {new_id}", s, flags=re.MULTILINE)
    # role_name -> New role (capitalized)
    role_name_val = new_id.replace("_", " ").title()
    s = re.sub(
        r"^role_name:\s*.+$", f"role_name: {role_name_val}", s, flags=re.MULTILINE
    )
    # name -> character name (e.g., Alex)
    s = re.sub(r"^name:\s*.+$", f"name: {character_name}", s, flags=re.MULTILINE)
    # responsibility_description
    if args.responsibility_description:
        if "responsibility_description:" in s:
            s = re.sub(
                r"responsibility_description:\s*\|?[\s\S]*?(?:\n(?=[A-Za-z_]+:)|\n$)",
                f"responsibility_description: |\n  {args.responsibility_description}\n",
                s,
            )
        else:
            s += f"\nresponsibility_description: |\n  {args.responsibility_description}\n"
    # introduction_words
    if args.introduction_words:
        if "introduction_words:" in s:
            s = re.sub(
                r"introduction_words:\s*\|?[\s\S]*?(?:\n(?=[A-Za-z_]+:)|\n$)",
                f"introduction_words: |\n  {args.introduction_words}\n",
                s,
            )
        else:
            s += f"\nintroduction_words: |\n  {args.introduction_words}\n"
    # tools block
    if args.tools:
        tools_block = "tools:\n" + "\n".join(f"- {t}" for t in args.tools) + "\n"
        if re.search(r"^tools:\s*\n(?:- .+\n)*", s, flags=re.MULTILINE):
            s = re.sub(r"^tools:\s*\n(?:- .+\n)*", tools_block, s, flags=re.MULTILINE)
        else:
            s += "\n" + tools_block

    # Update workflow filename
    def replace_workflow_field(text: str, new_val: str) -> str:
        import re

        # Helper to replace or append workflow inside a captured chat block
        def _replace_in_chat_block(header: str, body: str) -> str:
            wf_re = re.compile(
                r"(?m)^(\s*)(workflow\s*:\s*)(?:['\"]?)([^\n'\"]+)(?:['\"]?)\s*$"
            )
            if wf_re.search(body):
                return header + wf_re.sub(
                    lambda m: m.group(1) + m.group(2) + new_val, body, count=1
                )
            indent_match = re.match(r"^(\s*)", header)
            indent = indent_match.group(1) if indent_match else ""
            if not body.endswith("\n") and body != "":
                body = body + "\n"
            return header + body + f"{indent}  workflow: {new_val}\n"

        # Capture a chat: block (header + body up to next top-level key)
        chat_block_re = re.compile(
            r"(?P<header>^[ \t]*chat[ \t]*:[ \t]*\n)"
            r"(?P<body>(?:^(?![A-Za-z0-9_/-][^\n\r]*:\s).*\n)*)",
            flags=re.MULTILINE,
        )

        m = chat_block_re.search(text)
        if m:
            new_block = _replace_in_chat_block(m.group("header"), m.group("body"))
            start, end = m.span()
            return text[:start] + new_block + text[end:]

        # Replace top-level workflow if present
        top_re = re.compile(
            r"(?m)^(\s*workflow\s*:\s*)(?:['\"]?)([^\n'\"]+)(?:['\"]?)\s*$"
        )
        if top_re.search(text):
            return top_re.sub(rf"\1{new_val}", text, count=1)

        # If a bare chat: line exists, append workflow under it
        if re.search(r"(?m)^[ \t]*chat[ \t]*:[ \t]*$", text):
            return re.sub(
                r"(^[ \t]*chat[ \t]*:[ \t]*$)",
                rf"\1\n  workflow: {new_val}",
                text,
                count=1,
                flags=re.MULTILINE,
            )

        # Final fallback: append top-level workflow
        return text + f"\nworkflow: {new_val}\n"

    s = replace_workflow_field(s, f"{new_id}_workflow.json")
    role_yaml.write_text(s, encoding="utf-8")
    print(f"Updated {role_yaml} (workflow entry)")

    # 5. Update workflow json content (template_path + role.* keys)
    matched = list(new_role_dir.glob(f"*{new_id}*workflow.json"))
    print(f"DEBUG: workflow matches: {[p.name for p in matched]}")
    for p in matched:
        print(f"DEBUG: patching file: {p}")
        j = json.loads(p.read_text(encoding="utf-8"))
        j_s = json.dumps(j)

        # Replace Prompt.template_path for prompt_llm nodes
        j_s = re.sub(
            r'("id"\s*:\s*"prompt_llm"[\s\S]*?"params"\s*:\s*\{[\s\S]*?)("template_path"\s*:\s*)"config/prompts/[^"]+"',
            lambda m: m.group(1) + m.group(2) + f'"config/prompts/{new_id}.json"',
            j_s,
            flags=re.MULTILINE,
        )

        # Replace LLM agent params in llm_agent node
        j_s = re.sub(
            r'("id"\s*:\s*"llm_agent"[\s\S]*?"params"\s*:\s*\{)([\s\S]*?\})',
            lambda m: (
                m.group(1)
                + re.sub(
                    r'"model_name"\s*:\s*"role\.analyst\.llm\.ollama_model"',
                    f'"model_name":"role.{new_id}.llm.ollama_model"',
                    re.sub(
                        r'"provider"\s*:\s*"role\.analyst\.llm\.provider"',
                        f'"provider":"role.{new_id}.llm.provider"',
                        re.sub(
                            r'"host"\s*:\s*"role\.analyst\.llm\.ollama_host"',
                            f'"host":"role.{new_id}.llm.ollama_host"',
                            re.sub(
                                r'"options"\s*:\s*"role\.analyst\.llm\.generation_options"',
                                f'"options":"role.{new_id}.llm.generation_options"',
                                m.group(2),
                            ),
                        ),
                    ),
                )
            ),
            j_s,
            flags=re.MULTILINE,
        )

        # Replace Report.output_dir in report nodes
        j_s = re.sub(
            r'("id"\s*:\s*"report"[\s\S]*?"params"\s*:\s*\{)([\s\S]*?\})',
            lambda m: (
                m.group(1)
                + re.sub(
                    r'"output_dir"\s*:\s*"role\.analyst\.report\.output_dir"',
                    f'"output_dir":"role.{new_id}.report.output_dir"',
                    m.group(2),
                )
            ),
            j_s,
            flags=re.MULTILINE,
        )

        # Generic fallback replacements
        j_s = j_s.replace(
            "config/prompts/analyst.json", f"config/prompts/{new_id}.json"
        )
        j_s = re.sub(
            r"role\.analyst\.(llm\.[a-zA-Z0-9_\.]+)", rf"role.{new_id}.\1", j_s
        )

        # write back JSON (pretty-print if valid)
        try:
            j_out = json.loads(j_s)
            p.write_text(json.dumps(j_out, indent=2), encoding="utf-8")
        except Exception:
            p.write_text(j_s, encoding="utf-8")
        print(f"Patched workflow json: {p.name}")

    # 6. Clone gui/chat/role_turns package
    copy_tree(SRC_ROLE_TURNS, new_role_turns)

    # 7. Update handler.py and __init__.py replacements
    handler_py = new_role_turns / "handler.py"
    init_py = new_role_turns / "__init__.py"
    ensure_exists(handler_py, "handler.py in new role_turns")
    ensure_exists(init_py, "__init__.py in new role_turns")

    # Preserve any analyst_mode occurrences — do NOT replace analyst_mode with <new_role>_mode
    # Replace other tokens safely
    old_upper = SRC_ROLE.upper()
    new_upper = new_id.upper()
    replacements = {
        f"{old_upper}_ROLE_ID": f"{new_upper}_ROLE_ID",
        f"ORDERED_{old_upper}_TOOLS": f"ORDERED_{new_upper}_TOOLS",
        f"{SRC_ROLE}_workflow.json": f"{new_id}_workflow.json",
        "config/prompts/analyst.json": f"config/prompts/{new_id}.json",
        "AnalystChatHandler": f"{new_id.capitalize()}ChatHandler",
        # Do NOT replace 'analyst_mode' so preserve it as-is
    }
    replace_in_file(handler_py, replacements)
    replace_in_file(
        init_py,
        {
            "Analyst chat turn: analysis-focused tools, comments/todos only (no structural graph edits).": f"{new_id.capitalize()} chat turn: {new_id}-focused tools, comments/todos only (no structural graph edits).",
            "from .handler import AnalystChatHandler": f"from .handler import {new_id.capitalize()}ChatHandler",
            '__all__ = ["AnalystChatHandler"]': f'__all__ = ["{new_id.capitalize()}ChatHandler"]',
        },
    )

    # Update uppercase ANALYST token in handler.py but avoid touching 'analyst_mode'
    regex_replace_in_file(handler_py, r"\bANALYST\b", new_upper)
    # standalone 'analyst' word replacement: only replace occurrences that look like identifiers
    regex_replace_in_file(handler_py, r"\banalyst\b(?!_mode\b)", new_id)
    # docstring: """Analyst agents chat turn:...  -> """<New\_role> agents chat turn:
    regex_replace_in_file(
        handler_py,
        r'"""Analyst agents chat turn:',
        f'"""{new_id.capitalize()} agents chat turn:',
    )
    # rename workflow/prompt path constant identifiers and tool id list name
    regex_replace_in_file(
        handler_py,
        r"\b_ANALYST_WORKFLOW_PATH\b",
        f"_{new_id.upper()}_WORKFLOW_PATH",
    )
    regex_replace_in_file(
        handler_py,
        r"\b_ANALYST_PROMPT_PATH\b",
        f"_{new_id.upper()}_PROMPT_PATH",
    )
    regex_replace_in_file(
        handler_py,
        r"\banalyst_tool_ids\b",
        f"{new_id}_tool_ids",
    )

    # 7b plug in new role handler into the chat flow
    registry_py = _REPO_ROOT / "gui" / "chat" / "role_turns" / "registry.py"
    if registry_py.exists():
        # insert a new import line immediately before the existing analyst import,
        # preserving the same indentation as that line
        regex_replace_in_file(
            registry_py,
            r"^([ \t]*)from gui\.chat\.role_turns\.analyst import AnalystChatHandler",
            lambda m: (
                f"{m.group(1)}from gui.chat.role_turns.{new_id} import {new_id.capitalize()}ChatHandler\n{m.group(1)}from gui.chat.role_turns.analyst import AnalystChatHandler"
            ),
        )

        # insert the new handler construction after the RlCoachChatHandler() line,
        # preserving indentation by capturing the leading whitespace of that line
        regex_replace_in_file(
            registry_py,
            r"^(?P<indent>[ \t]*)cast\(RoleChatHandler,\s*RlCoachChatHandler\(\)\s*\),",
            lambda m: (
                f"{m.group('indent')}cast(RoleChatHandler, RlCoachChatHandler()),\n{m.group('indent')}cast(RoleChatHandler, {new_id.capitalize()}ChatHandler()),"
            ),
        )
        print(f"Updated {registry_py}")
    else:
        print(f"Warning: {registry_py} not found, skipping registry update")

    # 7c add the new role into the chat dropdown menu
    chat_py = _REPO_ROOT / "gui" / "chat" / "chat.py"
    if chat_py.exists():
        # add the ROLE_ID to the import tuple
        regex_replace_in_file(
            chat_py,
            r"from agents\.roles import \(\n([\s\S]*?)\n\)",
            lambda m: (
                "from agents.roles import (\n"
                + m.group(1)
                + f"\n    {new_id.upper()}_ROLE_ID,"
                + "\n)"
            ),
        )
        # add the ROLE_ID to the default dropdown tuple when _dropdown_role_ids is empty
        regex_replace_in_file(
            chat_py,
            r"_dropdown_role_ids = \(\n\s*WORKFLOW_DESIGNER_ROLE_ID,\n\s*ANALYST_ROLE_ID,\n\s*RL_COACH_ROLE_ID,\n\s*\)",
            f"_dropdown_role_ids = (\n            WORKFLOW_DESIGNER_ROLE_ID,\n            ANALYST_ROLE_ID,\n            RL_COACH_ROLE_ID,\n            {new_id.upper()}_ROLE_ID,\n        )",
        )
        print(f"Updated {chat_py}")
    else:
        print(f"Warning: {chat_py} not found, skipping chat.py update")

    # 8. Update agents/tools/catalog.py: add ordered tools and helper without breaking syntax
    if TOOLS_CATALOG.exists():
        s = TOOLS_CATALOG.read_text(encoding="utf-8")
        marker = f"ORDERED_{SRC_ROLE.upper()}_TOOLS"
        new_marker = f"ORDERED_{new_upper}_TOOLS"
        helper_name = f"{new_id}_tool_ids"
        if marker not in s:
            print(
                f"Warning: marker {marker} not found in {TOOLS_CATALOG}, skipping tools insertion"
            )
        elif new_marker in s:
            print(f"{new_marker} already present in {TOOLS_CATALOG}, skipping")
        else:
            # Find the 'ORDERED_<SRC>_TOOLS' assignment start
            m_start = re.search(
                rf"^\s*ORDERED_{re.escape(SRC_ROLE.upper())}_TOOLS\s*:.*=\s*\(",
                s,
                flags=re.M,
            )
            if not m_start:
                print(
                    f"Warning: couldn't locate start of ORDERED_{SRC_ROLE.upper()}_TOOLS in {TOOLS_CATALOG}, skipping"
                )
            else:
                start_idx = m_start.end() - 1  # index of the '('
                # scan forward to find the matching closing ')' for that tuple
                depth = 0
                end_idx = None
                for i in range(start_idx, len(s)):
                    ch = s[i]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
                if end_idx is None:
                    print(
                        f"Warning: unterminated tuple for ORDERED_{SRC_ROLE.upper()}_TOOLS, skipping"
                    )
                else:
                    tuple_block = s[m_start.start() : end_idx]
                    # extract (id, key) pairs from the tuple block
                    entries = re.findall(
                        r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)\s*,?', tuple_block
                    )
                    if not entries:
                        # fallback: extract from whole file
                        entries = re.findall(
                            r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)\s*,?', s
                        )
                    if not entries:
                        print(
                            f"Warning: no tool entries found to copy for {new_marker}, skipping"
                        )
                    else:
                        entries_text = ",\n    ".join(
                            f'("{a}", "{b}")' for a, b in entries
                        )
                        new_tuple = (
                            f"\n# {new_id.capitalize()} chat: full graph summary on demand; no read_code_block / run_workflow.\n"
                            f"{new_marker}: tuple[tuple[str, str], ...] = (\n"
                            f"    {entries_text},\n"
                            f")\n\n"
                        )
                        helper = (
                            f"def {helper_name}() -> tuple[str, ...]:\n"
                            f'    """Ordered tool ids for ``agents/roles/{new_id}/role.yaml`` ``tools``."""\n'
                            f"    return tuple(tid for tid, _ in {new_marker})\n\n"
                        )
                        insert_at = end_idx
                        s = s[:insert_at] + new_tuple + helper + s[insert_at:]
                        TOOLS_CATALOG.write_text(s, encoding="utf-8")
                        print(f"Appended {new_marker} and helper to {TOOLS_CATALOG}")
    else:
        print(f"Warning: tools catalog not found: {TOOLS_CATALOG}")

    # 9. Update roles/registry.py to add NEW_ROLE_ROLE_ID and chat order
    if ROLES_REGISTRY.exists():
        s = ROLES_REGISTRY.read_text(encoding="utf-8")
        const_name = f"{new_id.upper()}_ROLE_ID"
        const_line = f'{const_name} = "{new_id}"\n'
        if const_name not in s:
            if "ANALYST_ROLE_ID" in s:
                s = s.replace(
                    'ANALYST_ROLE_ID = "analyst"\n',
                    f'ANALYST_ROLE_ID = "analyst"\n{const_line}',
                )
            else:
                s = const_line + s
            s = re.sub(
                r"(CHAT_MAIN_agent_ROLE_IDS\s*:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\(\s*)([\s\S]*?)(\)\s*)",
                lambda m: m.group(1) + m.group(2) + f"    {const_name},\n" + m.group(3),
                s,
                flags=re.M,
            )
            ROLES_REGISTRY.write_text(s, encoding="utf-8")
            print(f"Updated {ROLES_REGISTRY} with {const_name}")
        else:
            print(f"{const_name} already defined in {ROLES_REGISTRY}, skipping")
    else:
        print(f"Warning: roles/registry.py not found: {ROLES_REGISTRY}")

    # 9.x Update agents/roles/__init__.py to export the new role id constant
    roles_init = Path("agents/roles") / "__init__.py"
    if roles_init.exists():
        s = roles_init.read_text(encoding="utf-8")
        new_const = f"{new_id.upper()}_ROLE_ID"
        # 1) import list insertion (after ANALYST_ROLE_ID)
        s = re.sub(
            r"(from agents.roles.registry import\s*\(\s*\n\s*ANALYST_ROLE_ID\s*,)",
            rf"\1\n    {new_const},",
            s,
            flags=re.M,
        )
        # 2) __all__ insertion (after \"ANALYST_ROLE_ID\",)
        s = re.sub(
            r'("ANALYST_ROLE_ID"\s*,)',
            rf'\1\n    "{new_const}",',
            s,
            flags=re.M,
        )
        if s != roles_init.read_text(encoding="utf-8"):
            roles_init.write_text(s, encoding="utf-8")
            print(f"Updated {roles_init} to export {new_const}")
        else:
            print(
                f"No changes made to {roles_init} (it may already include {new_const})"
            )
    else:
        print(f"Warning: {roles_init} not found, skipping __init__ update")

    # 10. Update role package module docstring in agents/roles/<new_role>/__init__.py
    role_init = new_role_dir / "__init__.py"
    if role_init.exists():
        s = role_init.read_text(encoding="utf-8")
        s_new = re.sub(
            r'"""Analyst role assets \(prompts, workflow JSON, input builders\)\."""',
            f'"""{new_id.replace("_", " ").title()} role assets (prompts, workflow JSON, input builders)."""',
            s,
            flags=re.M,
        )
        if s_new != s:
            role_init.write_text(s_new, encoding="utf-8")
            print(f"Updated docstring in {role_init}")
        else:
            print(f"No docstring change needed in {role_init}")
    else:
        print(f"Warning: {role_init} not found, skipping docstring update")

    # 11. Add import new role prompts into the nested agents/prompts.py for the prompt builder to access
    agents_prompts_py = _REPO_ROOT / "agents" / "prompts.py"
    if agents_prompts_py.exists():
        import_line = f"from agents.roles.{new_id}.prompts import *  # noqa: F403,E402"

        # Insert after the analyst import if present
        regex_replace_in_file(
            agents_prompts_py,
            r"(from agents\.roles\.analyst\.prompts import \*  # noqa: F403,E402\n)",
            lambda m: m.group(1) + import_line + "\n",
        )

        # If not inserted, try after the first role import block
        content = agents_prompts_py.read_text(encoding="utf-8")
        if import_line not in content:
            regex_replace_in_file(
                agents_prompts_py,
                r"(from agents\.roles\.[a-z0-9_]+\.prompts import \*  # noqa: F403,E402\n)",
                lambda m: m.group(1) + import_line + "\n",
            )

        # If still not present, insert before re-export comment or append at EOF
        content = agents_prompts_py.read_text(encoding="utf-8")
        if import_line not in content:
            if "# Re-export role prompt constants" in content:
                regex_replace_in_file(
                    agents_prompts_py,
                    r"# Re-export role prompt constants",
                    import_line + "\n\n# Re-export role prompt constants",
                )
            else:
                regex_replace_in_file(
                    agents_prompts_py,
                    r"\Z",
                    import_line + "\n",
                )

        print(f"Updated {agents_prompts_py}")
    else:
        print(
            f"Warning: {agents_prompts_py} not found, skipping agents/prompts.py update"
        )

    print("Done. The role has been successfully cloned.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--new-role", required=True, help="new role id (lowercase, underscored)"
    )
    ap.add_argument(
        "--character-name",
        required=True,
        help="character name to set in role.yaml (e.g., Alex)",
    )
    ap.add_argument("--responsibility", dest="responsibility_description", default=None)
    ap.add_argument("--intro", dest="introduction_words", default=None)
    ap.add_argument("--tools", nargs="*", default=[])
    args = ap.parse_args()
    main(args)
