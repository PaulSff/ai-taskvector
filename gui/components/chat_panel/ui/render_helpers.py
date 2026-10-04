from __future__ import annotations

import datetime
import json
import logging
import re
from collections.abc import Callable
from typing import Any

import flet as ft

from core.graph.todo_list import (
    add_task as _todo_add_task,
)
from core.graph.todo_list import create_new_todo_list as _create_new_todo_list
from core.graph.todo_list import (
    ensure_todo_lists as _todo_ensure_lists,
)
from core.graph.todo_list import (
    mark_completed as _todo_mark_completed,
)
from core.graph.todo_list import (
    remove_task as _todo_remove_task,
)
from core.schemas.process_graph import TodoList
from gui.components.chat_panel.ui.md_to_flet import md_blocks_to_controls, md_parser
from services.logging import setup_colored_logging

logger = setup_colored_logging(logging.DEBUG)

# Regex for fenced code blocks (```lang\n...\```)
_FENCE_RE = re.compile(
    r"```(?P<lang>[A-Za-z0-9_+-]+)?\n(?P<body>[\s\S]*?)```",
    re.MULTILINE,
)

_TRAILING_COMMA_BEFORE_CLOSE_RE = re.compile(r",(\s*[}\]])")

OPEN_FENCE_LINE = re.compile(r"```([A-Za-z0-9_+-]+)?\n")
_CLOSE_FENCE_LINE = re.compile(r"(?m)^```\s*$")

_QUERY_DISPLAY_ACTIONS = frozenset(
     {
         "search",
         "read_file",
         "web_search",
         "browse",
         "github",
         "read_code_block",
         "grep",
         "delegate_request",
     }
 )

_TODO_DISPLAY_ACTIONS = frozenset(
     {
         "add_todo_list",
         "remove_todo_list",
         "add_task",
         "remove_task",
         "mark_completed",
     }
 )

_TODO_MUTATOR_ONLY_ACTIONS = frozenset(
     {
         "mark_completed",
         "remove_task",
         "remove_todo_list",
     }
 )
# The content inside fenced blocks containing the actions below
# is going to be hidden for UI performace
# (e.g. edit file content is not required to be displayed to the user).
# TODO: sync the actions with the tools registry instead of hardcoding
HIDE_ACTIONS = {
    "edit_file",
    "delegate_request",
    "new_file",
    "read_file",
    "no_action",
    "web_search",
    "browse",
    "search",
    "calendar",
    "add_comment",
    "remove_comment",
    "list_dir",
    "report",
    "add_todo_list",
    "remove_todo_list",
    "add_task",
    "remove_task",
    "set_implementer",
    "set_deadline",
    "set_curator",
    "set_todo_list_title",
    "mark_completed",
    "read_current_workflow",
    "make_dir",
    "replace_graph",
}

# Define the hidden actions parsing pattern
_ACTION_RE = re.compile(
    r'"action"\s*:\s*"(edit_file|delegate_request|new_file|read_file|no_action|'
    r'web_search|browse|search|calendar|add_comment|remove_comment|list_dir|report|'
    r'add_todo_list|remove_todo_list|add_task|remove_task|set_implementer|set_deadline|'
    r'set_curator|set_todo_list_title|read_current_workflow|make_dir|replace_graph|mark_completed)"'
)


def fence_is_hidden_action(text: str) -> bool:
    return _ACTION_RE.search(text) is not None


def _line_start_positions(text: str):
    lines = text.splitlines(keepends=True)
    pos = [0]
    cur = 0
    for ln in lines:
        cur += len(ln)
        pos.append(cur)
    return lines, pos  # pos[i] is start offset of line i


def find_closing_fence(text: str, start_idx: int):
    lines, starts = _line_start_positions(text)

    # Find the first fence line at/after start_idx (opening)
    start_line = None
    for i, ln in enumerate(lines):
        if starts[i] + len(ln) <= start_idx:
            continue
        candidate = ln.rstrip("\r\n")
        if OPEN_FENCE_LINE.match(candidate):
            start_line = i
            break

    if start_line is None:
        return None

    # Closing fence is the first standalone ``` after the opening line
    for j in range(start_line + 1, len(lines)):
        candidate = lines[j].rstrip("\r\n")
        if _CLOSE_FENCE_LINE.match(candidate):
            return starts[j]  # absolute offset of closing fence line start

    return None

def tex_arrows_to_unicode(s: str) -> str:
    return (
        s.replace(r"$\rightarrow$", "→")
        .replace(r"\rightarrow", "→")
        .replace(r"\to", "→")
        .replace(r"\longrightarrow", "⟶")
        .replace(r"\mapsto", "↦")
        .replace(r"$\leftarrow$", "←")
        .replace(r"\leftarrow", "←")
        .replace(r"\leftrightarrow", "↔")
    )


def build_agent_plain_text_control(
    chunk: str,
    *,
    text_style: ft.TextStyle,
    bubble_width: int | None,
) -> ft.Control | None:
    chunk = tex_arrows_to_unicode(chunk)
    try:
        tokens = md_parser.parse(chunk)
        controls = md_blocks_to_controls(tokens, text_style, bubble_width)
        if not controls:
            return ft.Text(
                "", style=text_style, selectable=True, no_wrap=False, width=bubble_width
            )
        if len(controls) == 1:
            return controls[0]
        return ft.Column(controls=controls, spacing=4, tight=True)
    except (ValueError, TypeError):
        return ft.Text(
            chunk, style=text_style, selectable=True, no_wrap=False, width=bubble_width
        )


def split_fenced_blocks(text: str) -> list[tuple[str, str | None, str]]:
    parts: list[tuple[str, str | None, str]] = []
    last = 0

    for m in _FENCE_RE.finditer(text):
        if m.start() > last:
            parts.append(("text", None, text[last:m.start()]))

        lang = m.group("lang") or None
        body = m.group("body") or ""

        # If this is a JSON fence and still very short, keep it undecided
        # so we don't prematurely render it as code before it can become hidden.
        if lang == "json" and len(body) < 42:
            parts.append(("text", None, m.group(0)))
            last = m.end()
            continue

        kind = "hidden" if (
            fence_is_hidden_action(body) or parsed_is_query_display_only(body)
        ) else "code"
        parts.append((kind, lang, body))
        last = m.end()

    tail = text[last:]
    if not tail:
        return parts

    last_open: re.Match[str] | None = None
    for m in OPEN_FENCE_LINE.finditer(tail):
        last_open = m

    if last_open is None:
        parts.append(("text", None, tail))
        return parts

    prefix = tail[: last_open.start()]
    if prefix:
        parts.append(("text", None, prefix))

    lang = last_open.group(1) or None
    body = tail[last_open.end():]

    if lang == "json" and len(body) < 33:
        parts.append(("text", None, tail[last_open.start():]))
        return parts

    kind = "hidden" if (
        fence_is_hidden_action(body) or parsed_is_query_display_only(body)
    ) else "code"
    parts.append((kind, lang, body))
    return parts


def compact_meta_text_style(
    *,
    bubble_width: int | None,
) -> dict[str, Any]:
    return {
        "size": 11,
        "color": ft.Colors.with_opacity(
            0.85,
            ft.Colors.GREY_400,
        ),
        "selectable": True,
        "no_wrap": False,
        "width": bubble_width,
    }


def try_salvage_json_value(s: str) -> Any | None:
    raw = s.strip()
    if not raw:
        return None

    # 1) Raw parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2) Remove trailing commas before } or ]
    compact = raw
    for _ in range(3):  # a few passes
        new = _TRAILING_COMMA_BEFORE_CLOSE_RE.sub(r"\1", compact)
        if new == compact:
            break
        compact = new
        try:
            return json.loads(compact)
        except json.JSONDecodeError:
            pass

    # 3) Append missing closing braces/brackets if we can tell depth at end
    depth = 0
    in_string = False
    escape = False
    saw_brace_or_bracket = False
    last_open_stack: list[str] = []

    for ch in compact:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "{[":
            depth += 1
            saw_brace_or_bracket = True
            last_open_stack.append(ch)
        elif ch in "}]":
            depth -= 1
            if depth < 0:
                return None
            if last_open_stack:
                last_open_stack.pop()

    if in_string or not saw_brace_or_bracket:
        return None

    if depth > 0:
        closers = []
        # last_open_stack holds openers in order encountered; close in reverse.
        for opener in reversed(last_open_stack):
            closers.append("}" if opener == "{" else "]")
        candidate = compact + "".join(closers)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    return None


def truncate_display(
    s: Any,
    max_len: int = 140,
) -> str:
    t = "" if s is None else str(s).strip().replace("\n", " ")

    if len(t) > max_len:
        return t[: max_len - 1] + "…"

    return t


def iter_action_dicts(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, dict):
        edits = parsed.get("edits")

        if isinstance(edits, list) and edits:
            return [e for e in edits if isinstance(e, dict) and e.get("action")]

        if parsed.get("action") is not None:
            return [parsed]

        return []

    if isinstance(parsed, list):
        return [e for e in parsed if isinstance(e, dict) and e.get("action")]

    return []


def parsed_is_no_action_only(parsed: Any) -> bool:
    if isinstance(parsed, dict):
        if parsed.get("action") == "no_action":
            return True

        edits = parsed.get("edits")

        if isinstance(edits, list) and edits:
            return all(
                isinstance(e, dict) and e.get("action") == "no_action" for e in edits
            )

    if isinstance(parsed, list):
        return all(isinstance(e, dict) and e.get("action") == "no_action" for e in parsed)

    return False


def parsed_is_query_display_only(parsed: Any) -> bool:
    items = iter_action_dicts(parsed)

    if not items:
        return False

    return all((e.get("action") or "") in _QUERY_DISPLAY_ACTIONS for e in items)


def parsed_is_todo_display_only(parsed: Any) -> bool:
    items = iter_action_dicts(parsed)

    if not items:
        return False

    return all((e.get("action") or "") in _TODO_DISPLAY_ACTIONS for e in items)


def parsed_is_todo_mutators_only(parsed: Any) -> bool:
    items = iter_action_dicts(parsed)

    if not items:
        return False

    return all((e.get("action") or "") in _TODO_MUTATOR_ONLY_ACTIONS for e in items)


def compact_line_with_optional_success_icon(
    line: str,
    *,
    bubble_width: int | None,
    show_success_icon: bool,
) -> ft.Control:

    if not show_success_icon:
        return ft.Text(
            line,
            **compact_meta_text_style(
                bubble_width=bubble_width,
            ),
        )

    return ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.CHECK_CIRCLE,
                size=12,
                color=ft.Colors.with_opacity(
                    0.95,
                    ft.Colors.GREEN_400,
                ),
            ),
            ft.Text(
                line,
                **compact_meta_text_style(
                    bubble_width=bubble_width,
                ),
            ),
        ],
        spacing=5,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        width=bubble_width,
    )


def todo_mutator_summary_lines(
    items: list[dict[str, Any]],
) -> list[str]:

    lines: list[str] = []

    for d in items:
        act = (d.get("action") or "").strip()

        if act == "mark_completed":
            tid = truncate_display(
                d.get("task_id"),
                100,
            )

            lines.append(f"Mark task complete: {tid}" if tid else "Mark task complete")

        elif act == "remove_task":
            tid = truncate_display(
                d.get("task_id"),
                100,
            )

            lines.append(f"Remove task: {tid}" if tid else "Remove task")

        elif act == "remove_todo_list":
            lines.append("Remove todo list")

        else:
            lines.append(act or "Todo update")

    return lines


def simulate_todo_actions(
    items: list[dict[str, Any]],
) -> tuple[
    TodoList | None,
    list[str],
    bool,
]:
    todo_lists: list[TodoList] | None = None
    warnings: list[str] = []
    list_explicitly_removed = False

    for d in items:
        act = (d.get("action") or "").strip()

        try:
            if act == "add_todo_list":
                title = d.get("title")
                list_id = d.get("list_id") or d.get("id")

                todo_lists = _create_new_todo_list(
                    todo_lists or [],
                    title=(
                        str(title).strip()
                        if title is not None and str(title).strip()
                        else None
                    ),
                    list_id=(
                        str(list_id).strip()
                        if list_id is not None and str(list_id).strip()
                        else None
                    ),
                )

            elif act == "remove_todo_list":
                todo_lists = None
                list_explicitly_removed = True

            elif act == "add_task":
                text = d.get("text")
                if not text or not str(text).strip():
                    raise ValueError("add_task: missing text")

                todo_lists = _todo_ensure_lists(todo_lists)
                if not todo_lists:
                    raise ValueError("add_task: no todo_list present")

                tid = d.get("task_id")
                task_id = (
                    str(tid).strip()
                    if tid is not None and str(tid).strip()
                    else None
                )

                todo_lists[0] = _todo_add_task(
                    todo_lists[0],
                    str(text).strip(),
                    task_id=task_id,
                )

            elif act == "remove_task":
                tid = d.get("task_id")
                if not tid or not str(tid).strip():
                    raise ValueError("remove_task: missing task_id")

                todo_lists = _todo_ensure_lists(todo_lists)
                if not todo_lists:
                    raise ValueError("remove_task: no todo_list present")

                todo_lists[0] = _todo_remove_task(
                    todo_lists[0],
                    str(tid).strip(),
                )

            elif act == "mark_completed":
                tid = d.get("task_id")
                if not tid or not str(tid).strip():
                    raise ValueError("mark_completed: missing task_id")

                todo_lists = _todo_ensure_lists(todo_lists)
                if not todo_lists:
                    raise ValueError("mark_completed: no todo_list present")

                completed = d.get("completed", True)

                if isinstance(completed, str):
                    completed = completed.strip().lower() in {
                        "1",
                        "true",
                        "yes",
                    }

                todo_lists[0] = _todo_mark_completed(
                    todo_lists[0],
                    str(tid).strip(),
                    completed=bool(completed),
                )

        except ValueError as e:
            warnings.append(str(e))

    final_todo_list = todo_lists[0] if todo_lists else None

    return (
        final_todo_list,
        warnings,
        list_explicitly_removed,
    )


def build_todo_preview_controls(
    todo_list: TodoList | None,
    warnings: list[str],
    *,
    list_explicitly_removed: bool,
    bubble_width: int | None,
) -> list[ft.Control]:
    out: list[ft.Control] = []

    for warning in warnings:
        out.append(
            ft.Text(
                f"⚠ {warning}",
                size=10,
                color=ft.Colors.with_opacity(
                    0.9,
                    ft.Colors.AMBER_400,
                ),
                selectable=True,
                no_wrap=False,
                width=bubble_width,
            )
        )

    if todo_list is None:
        if list_explicitly_removed:
            message = "Todo list removed."
        elif warnings:
            message = "Todo list preview unavailable (fix errors above)."
        else:
            message = "No todo list."

        out.append(
            ft.Text(
                message,
                **compact_meta_text_style(
                    bubble_width=bubble_width,
                ),
            )
        )
        return out

    title = (todo_list.title or "").strip()

    if title:
        out.append(
            ft.Text(
                title,
                size=12,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.GREY_200,
                selectable=True,
                no_wrap=False,
                width=bubble_width,
            )
        )

    tasks = todo_list.tasks

    if not tasks:
        out.append(
            ft.Text(
                "No tasks in the list.",
                **compact_meta_text_style(
                    bubble_width=bubble_width,
                ),
            )
        )
        return out

    for task in tasks:
        text = (task.text or "").strip() or "(empty task)"
        completed = bool(task.completed)

        body_style = ft.TextStyle(
            size=12,
            color=ft.Colors.with_opacity(
                0.85 if completed else 1.0,
                ft.Colors.GREY_400 if completed else ft.Colors.GREY_200,
            ),
            decoration=(
                ft.TextDecoration.LINE_THROUGH
                if completed
                else None
            ),
        )

        out.append(
            ft.Row(
                controls=[
                    ft.Icon(
                        (
                            ft.Icons.CHECK_BOX_ROUNDED
                            if completed
                            else ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED
                        ),
                        size=20,
                        color=ft.Colors.with_opacity(
                            0.95,
                            ft.Colors.GREEN_400
                            if completed
                            else ft.Colors.GREY_500,
                        ),
                    ),
                    ft.Text(
                        text,
                        style=body_style,
                        selectable=True,
                        no_wrap=False,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                width=bubble_width,
            )
        )

    return out


def _query_action_summary_line(
    d: dict[str, Any],
) -> str:
    act = (d.get("action") or "").strip()

    if act == "search":
        q = truncate_display(d.get("query"), 120)
        return f'Knowledge base search: "{q}"' if q else "Knowledge base search"

    if act == "read_file":
        p = truncate_display(d.get("path"), 200)
        return f"Read file: {p}" if p else "Read file"

    if act == "web_search":
        q = truncate_display(d.get("query"), 120)
        return f'Web search: "{q}"' if q else "Web search"

    if act == "browse":
        u = truncate_display(d.get("url"), 160)
        return f"Browse: {u}" if u else "Browse URL"

    if act == "github":
        pl = d.get("payload")

        ga = ""

        if isinstance(pl, dict):
            ga = str(pl.get("action") or "").strip()

        return f"GitHub: {truncate_display(ga, 100)}" if ga else "GitHub request"

    if act == "read_code_block":
        uid = truncate_display(d.get("id"), 80)
        return f"Request code block: {uid}" if uid else "Request code block"

    if act == "read_current_workflow":
        return "Full graph summary"

    if act == "grep":
        pat = truncate_display(d.get("pattern"), 100)

        src = d.get("source")

        src_t = truncate_display(src, 80) if src else ""

        if pat and src_t:
            return f'Grep "{pat}" in {src_t}'

        if pat:
            return f'Grep: "{pat}"'

        return "Grep"

    if act == "delegate_request":
        delegate_to = d.get("delegate_to")  # None when JSON null
        if delegate_to is None:
            return "Self-handling"
        to = truncate_display(delegate_to, 80)
        return f"Assigned to: {to}" if to else "Self-handling"

    return act or "Request"


def build_feedback_thumbs(msg: dict[str, Any], persist: Callable[[], None]) -> ft.Row:
    """Thumb up / down strip appended below every agent message bubble."""

    def _current_value() -> str | None:
        fb = msg.get("feedback")
        return fb.get("value") if isinstance(fb, dict) else None

    up_ref: list[ft.IconButton | None] = [None]
    dn_ref: list[ft.IconButton | None] = [None]

    def _refresh() -> None:
        val = _current_value()
        for btn, match in ((up_ref[0], "up"), (dn_ref[0], "down")):
            if btn is None:
                continue
            btn.icon_color = (
                ft.Colors.GREEN_400
                if match == "up" and val == "up"
                else ft.Colors.RED_400
                if match == "down" and val == "down"
                else ft.Colors.GREY_700
            )
            try:
                btn.update()
            except (ValueError, TypeError):
                pass

    def _on_thumb(value: str) -> Callable[[ft.Event[ft.IconButton]], None]:
        def _handler(_e: ft.Event[ft.IconButton]) -> None:
            if _current_value() == value:
                msg.pop("feedback", None)
            else:
                msg["feedback"] = {
                    "type": "thumb",
                    "value": value,
                    "ts": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                }
            _refresh()
            persist()

        return _handler

    _btn_style = ft.ButtonStyle(
        padding=2,
        shape=ft.RoundedRectangleBorder(radius=4),
    )
    val = _current_value()

    up_btn = ft.IconButton(
        icon=ft.Icons.THUMB_UP_OUTLINED,
        icon_size=13,
        width=20,
        height=20,
        style=_btn_style,
        icon_color=ft.Colors.GREEN_400 if val == "up" else ft.Colors.GREY_700,
        tooltip="Good response",
        on_click=_on_thumb("up"),
    )
    dn_btn = ft.IconButton(
        icon=ft.Icons.THUMB_DOWN_OUTLINED,
        icon_size=13,
        width=20,
        height=20,
        style=_btn_style,
        icon_color=ft.Colors.RED_400 if val == "down" else ft.Colors.GREY_700,
        tooltip="Bad response",
        on_click=_on_thumb("down"),
    )
    up_ref[0] = up_btn
    dn_ref[0] = dn_btn

    return ft.Row(controls=[up_btn, dn_btn], spacing=2, tight=True)


def query_display_lines(parsed: Any) -> list[str]:
    return [_query_action_summary_line(d) for d in iter_action_dicts(parsed)]


def extract_edit_action(
    parsed: Any,
) -> str | None:
    if not parsed:
        return None

    if isinstance(parsed, dict):
        action = parsed.get("action")

        if action not in (None, "no_action"):
            return action

        edits = parsed.get("edits")

        if isinstance(edits, list):
            for e in edits:
                if isinstance(e, dict):
                    a = e.get("action")

                    if a not in (None, "no_action"):
                        return a

    if isinstance(parsed, list):
        for e in parsed:
            if isinstance(e, dict):
                a = e.get("action")

                if a not in (None, "no_action"):
                    return a

    return None
