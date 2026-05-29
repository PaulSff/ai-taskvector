from __future__ import annotations

import json
import re
from typing import Any, Callable, cast

import flet as ft
from flet import Border, BorderSide

from core.graph.todo_list import (
    add_task as _todo_add_task,
)
from core.graph.todo_list import (
    ensure_todo_list as _todo_ensure_list,
)
from core.graph.todo_list import (
    mark_completed as _todo_mark_completed,
)
from core.graph.todo_list import (
    remove_task as _todo_remove_task,
)
from gui.chat.ui.md_table_to_flet import markdown_table_to_datatable
from gui.utils.code_editor import build_code_display

# Regex for fenced code blocks (```lang\n...\```)
_FENCE_RE = re.compile(
    r"```(?P<lang>[A-Za-z0-9_+-]+)?\n(?P<body>[\s\S]*?)```",
    re.MULTILINE,
)

_OPEN_FENCE_LINE = re.compile(r"```([A-Za-z0-9_+-]+)?\n")
_CLOSE_FENCE_LINE = re.compile(r"(?m)^```\s*$")

_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*([:;.,!?])?", re.DOTALL)
# regex for ATX headers: capture level (1-6) and the header text (strip trailing hashes/spaces)
_MARKDOWN_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:#+\s*)?$", re.MULTILINE)

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


def _tex_arrows_to_unicode(s: str) -> str:
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


_CODE_SPAN_RE = re.compile(r"`([^`]+)`")


def _find_markdown_table_block(s: str) -> tuple[int, int] | None:
    """
    Find a pipe-table block in s and return (start_index, end_index) of the block,
    or None if none found.
    """
    lines = s.splitlines(keepends=True)
    n = len(lines)
    i = 0
    while i < n:
        # look for a potential header line containing at least one pipe
        if "|" not in lines[i]:
            i += 1
            continue

        # header candidate at i; need a separator line at i+1
        if i + 1 >= n:
            break
        sep = lines[i + 1].strip()
        # separator must contain only pipes, colons, hyphens and spaces, and at least one hyphen
        if "|" in sep and re.fullmatch(r"[\|\:\-\s]+", sep) and "-" in sep:
            # consume subsequent table rows that contain at least one pipe
            j = i + 2
            while j < n and ("|" in lines[j]):
                j += 1
            # return indices into the original string
            start = sum(len(x) for x in lines[:i])
            end = sum(len(x) for x in lines[:j])
            return (start, end)
        i += 1
    return None


def _assistant_text_segments_with_code_and_bold(chunk: str) -> list[tuple[str, str]]:
    if not chunk:
        return []
    # first convert TeX arrows
    chunk = _tex_arrows_to_unicode(chunk)

    tbl_range = _find_markdown_table_block(chunk)
    if tbl_range:
        start, end = tbl_range
        table_block = chunk[start:end]
        return [(table_block, "table")]

    # handle ATX headers (return header text and a "headerN" kind where N is level)
    m = _MARKDOWN_HEADER_RE.match(chunk)
    if m:
        level = len(m.group(1))
        return [(m.group(2), f"header{level}")]

    parts: list[tuple[str, str]] = []
    last = 0
    for m in _CODE_SPAN_RE.finditer(chunk):
        if m.start() > last:
            seg = chunk[last : m.start()]
            for bm in _MARKDOWN_BOLD_RE.finditer(seg):
                bstart = bm.start()
                bend = bm.end()
                if bstart > 0:
                    parts.append((seg[:bstart], "plain"))
                parts.append((bm.group(1), "bold"))
                # optional trailing punctuation captured in group 2 (if using option 2)
                if bm.lastindex and bm.group(2):
                    parts.append((bm.group(2), "plain"))
                seg = seg[bend:]
                last = 0
            if seg:
                parts.append((seg, "plain"))
        parts.append((m.group(1), "code"))
        last = m.end()
    if last < len(chunk):
        parts.append((chunk[last:], "plain"))
    return parts if parts else [(chunk, "plain")]


def _text_style_bold_variant(base: ft.TextStyle) -> ft.TextStyle:
    return ft.TextStyle(
        size=getattr(base, "size", None),
        color=getattr(base, "color", None),
        weight=ft.FontWeight.W_600,
        font_family=getattr(base, "font_family", None),
        italic=getattr(base, "italic", False),
    )


def _build_assistant_plain_text_control(
    chunk: str,
    *,
    text_style: ft.TextStyle,
    bubble_width: int | None,
) -> ft.Control:
    segs = _assistant_text_segments_with_code_and_bold(chunk)

    # fast path: single table segment
    if len(segs) == 1 and segs[0][1] == "table":
        table_block = segs[0][0] or ""
        try:
            tables = markdown_table_to_datatable(table_block, text_style)
        except Exception:
            return ft.Text(
                table_block,
                style=text_style,
                selectable=True,
                no_wrap=False,
                width=bubble_width,
            )
        # if markdown_table_to_datatable returns a list, wrap them in Containers
        controls: list[ft.Control] = []
        for tbl in tables:
            controls.append(
                ft.Container(
                    content=tbl,
                    padding=ft.padding.all(2),
                    width=bubble_width,
                    border=Border(
                        bottom=BorderSide(0.6, ft.Colors.GREY_800),
                    ),
                    bgcolor=ft.Colors.SURFACE,
                )
            )
        return ft.Column(controls=controls, tight=True)

    spans: list[ft.TextSpan] = []
    mono_family = "monospace"

    # determine if single-segment simple fast path (plain or header)
    if len(segs) == 1:
        single_kind = segs[0][1]
        single_fragment = segs[0][0] or ""
        if single_kind == "plain":
            return ft.Text(
                single_fragment,
                style=text_style,
                selectable=True,
                no_wrap=False,
                width=bubble_width,
            )
        if single_kind.startswith("header"):
            level = (
                int(single_kind[len("header") :])
                if single_kind[len("header") :].isdigit()
                else 2
            )
            base_size = getattr(text_style, "size", 14) or 14
            header_size = base_size + max(0, 3 - level) * 2  # sizing
            header_style = ft.TextStyle(
                size=header_size,
                weight=ft.FontWeight.W_700,
                color=getattr(text_style, "color", ft.Colors.GREY_400),
            )
            return ft.Text(
                single_fragment,
                style=header_style,
                selectable=True,
                no_wrap=False,
                width=bubble_width,
            )

    for fragment, kind in segs:
        if not fragment:
            continue

        if kind == "table":
            try:
                tables = markdown_table_to_datatable(fragment, text_style)
            except Exception:
                spans.append(ft.TextSpan(fragment, style=text_style))
                continue

            # build controls for each table
            table_controls: list[ft.Control] = [
                ft.Container(
                    content=tbl,
                    padding=ft.padding.all(2),
                    width=bubble_width,
                    border=Border(
                        bottom=BorderSide(0.6, ft.Colors.GREY_800),
                    ),
                    bgcolor=ft.Colors.SURFACE,
                )
                for tbl in tables
            ]

            if spans:
                # return combined text then tables
                return ft.Column(
                    controls=[
                        ft.Text(
                            spans=spans,
                            selectable=True,
                            no_wrap=False,
                            width=bubble_width,
                        ),
                        *table_controls,
                    ],
                    tight=True,
                )
            else:
                # only tables
                return ft.Column(controls=table_controls, tight=True)

        if kind == "code":
            style = ft.TextStyle(
                size=getattr(text_style, "size", None),
                color=getattr(text_style, "color", ft.Colors.GREY_600),
                font_family=mono_family,
                weight=ft.FontWeight.W_600,
                bgcolor=ft.Colors.GREY_900,
            )
        elif kind == "bold":
            style = _text_style_bold_variant(text_style)
        elif kind.startswith("header"):
            level = int(kind[len("header") :]) if kind[len("header") :].isdigit() else 2
            base_size = getattr(text_style, "size", 14) or 14
            header_size = base_size + max(0, 3 - level) * 2
            style = ft.TextStyle(
                size=header_size,
                weight=ft.FontWeight.W_700,
                color=getattr(text_style, "color", ft.Colors.GREY_600),
            )
        else:
            style = text_style

        spans.append(ft.TextSpan(fragment, style=style))

    # fallback: assemble Text from spans
    return ft.Text(spans=spans, selectable=True, no_wrap=False, width=bubble_width)


def _split_fenced_blocks(
    text: str,
) -> list[tuple[str, str | None, str]]:
    parts: list[tuple[str, str | None, str]] = []

    last = 0

    for m in _FENCE_RE.finditer(text):
        if m.start() > last:
            parts.append(("text", None, text[last : m.start()]))

        parts.append(
            (
                "code",
                m.group("lang") or None,
                m.group("body") or "",
            )
        )

        last = m.end()

    tail = text[last:]

    if not tail:
        return parts

    last_open: re.Match[str] | None = None

    for m in _OPEN_FENCE_LINE.finditer(tail):
        last_open = m

    if last_open is None:
        parts.append(("text", None, tail))
        return parts

    body = tail[last_open.end() :]

    if _CLOSE_FENCE_LINE.search(body):
        parts.append(("text", None, tail))
        return parts

    prefix = tail[: last_open.start()]

    if prefix:
        parts.append(("text", None, prefix))

    parts.append(
        (
            "code",
            last_open.group(1) or None,
            body,
        )
    )

    return parts


def _compact_meta_text_style(
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


def _truncate_display(
    s: Any,
    max_len: int = 140,
) -> str:
    t = "" if s is None else str(s).strip().replace("\n", " ")

    if len(t) > max_len:
        return t[: max_len - 1] + "…"

    return t


def _iter_action_dicts(parsed: Any) -> list[dict[str, Any]]:
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


def _parsed_is_no_edit_only(parsed: Any) -> bool:
    if isinstance(parsed, dict):
        if parsed.get("action") == "no_edit":
            return True

        edits = parsed.get("edits")

        if isinstance(edits, list) and edits:
            return all(
                isinstance(e, dict) and e.get("action") == "no_edit" for e in edits
            )

    if isinstance(parsed, list):
        return all(isinstance(e, dict) and e.get("action") == "no_edit" for e in parsed)

    return False


def _parsed_is_query_display_only(parsed: Any) -> bool:
    items = _iter_action_dicts(parsed)

    if not items:
        return False

    return all((e.get("action") or "") in _QUERY_DISPLAY_ACTIONS for e in items)


def _parsed_is_todo_display_only(parsed: Any) -> bool:
    items = _iter_action_dicts(parsed)

    if not items:
        return False

    return all((e.get("action") or "") in _TODO_DISPLAY_ACTIONS for e in items)


def _parsed_is_todo_mutators_only(parsed: Any) -> bool:
    items = _iter_action_dicts(parsed)

    if not items:
        return False

    return all((e.get("action") or "") in _TODO_MUTATOR_ONLY_ACTIONS for e in items)


def _compact_line_with_optional_success_icon(
    line: str,
    *,
    bubble_width: int | None,
    show_success_icon: bool,
) -> ft.Control:

    if not show_success_icon:
        return ft.Text(
            line,
            **_compact_meta_text_style(
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
                **_compact_meta_text_style(
                    bubble_width=bubble_width,
                ),
            ),
        ],
        spacing=5,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        width=bubble_width,
    )


def _todo_mutator_summary_lines(
    items: list[dict[str, Any]],
) -> list[str]:

    lines: list[str] = []

    for d in items:
        act = (d.get("action") or "").strip()

        if act == "mark_completed":
            tid = _truncate_display(
                d.get("task_id"),
                100,
            )

            lines.append(f"Mark task complete: {tid}" if tid else "Mark task complete")

        elif act == "remove_task":
            tid = _truncate_display(
                d.get("task_id"),
                100,
            )

            lines.append(f"Remove task: {tid}" if tid else "Remove task")

        elif act == "remove_todo_list":
            lines.append("Remove todo list")

        else:
            lines.append(act or "Todo update")

    return lines


def _simulate_todo_actions(
    items: list[dict[str, Any]],
) -> tuple[
    dict[str, Any] | None,
    list[str],
    bool,
]:

    todo_list: dict[str, Any] | None = None

    warnings: list[str] = []

    list_explicitly_removed = False

    for d in items:
        act = (d.get("action") or "").strip()

        try:
            if act == "add_todo_list":
                todo_list = _todo_ensure_list(todo_list)

                title = d.get("title")

                if title is not None and str(title).strip():
                    todo_list = {
                        **todo_list,
                        "title": str(title).strip(),
                    }

            elif act == "remove_todo_list":
                todo_list = None
                list_explicitly_removed = True

            elif act == "add_task":
                text = d.get("text")

                if not text or not str(text).strip():
                    raise ValueError("add_task: missing text")

                todo_list = _todo_ensure_list(todo_list)

                tid = d.get("task_id")

                tid_s = str(tid).strip() if tid is not None else None

                todo_list = _todo_add_task(
                    todo_list,
                    str(text).strip(),
                    task_id=tid_s or None,
                )

            elif act == "remove_task":
                tid = d.get("task_id")

                if not tid or not str(tid).strip():
                    raise ValueError("remove_task: missing task_id")

                todo_list = _todo_ensure_list(todo_list)

                todo_list = _todo_remove_task(
                    todo_list,
                    str(tid).strip(),
                )

            elif act == "mark_completed":
                tid = d.get("task_id")

                if not tid or not str(tid).strip():
                    raise ValueError("mark_completed: missing task_id")

                todo_list = _todo_ensure_list(todo_list)

                completed = d.get(
                    "completed",
                    True,
                )

                if isinstance(completed, str):
                    completed = completed.strip().lower() in ("1", "true", "yes")

                todo_list = _todo_mark_completed(
                    todo_list,
                    str(tid).strip(),
                    completed=bool(completed),
                )

        except ValueError as e:
            warnings.append(str(e))

    return (
        todo_list,
        warnings,
        list_explicitly_removed,
    )


def _build_todo_preview_controls(
    todo_list: dict[str, Any] | None,
    warnings: list[str],
    *,
    list_explicitly_removed: bool,
    bubble_width: int | None,
) -> list[ft.Control]:

    out: list[ft.Control] = []

    for w in warnings:
        out.append(
            ft.Text(
                f"⚠ {w}",
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
            out.append(
                ft.Text(
                    "Todo list removed.",
                    **_compact_meta_text_style(
                        bubble_width=bubble_width,
                    ),
                )
            )

        elif warnings:
            out.append(
                ft.Text(
                    "Todo list preview unavailable (fix errors above).",
                    **_compact_meta_text_style(
                        bubble_width=bubble_width,
                    ),
                )
            )

        else:
            out.append(
                ft.Text(
                    "No todo list.",
                    **_compact_meta_text_style(
                        bubble_width=bubble_width,
                    ),
                )
            )

        return out

    title = (todo_list.get("title") or "").strip()

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

    tasks_raw = todo_list.get("tasks") or []

    tasks = [t for t in tasks_raw if isinstance(t, dict)]

    if not tasks:
        out.append(
            ft.Text(
                "No tasks in list.",
                **_compact_meta_text_style(
                    bubble_width=bubble_width,
                ),
            )
        )

        return out

    for t in tasks:
        text = (t.get("text") or "").strip() or "(empty task)"

        completed = bool(t.get("completed"))

        body_style = ft.TextStyle(
            size=12,
            color=ft.Colors.with_opacity(
                0.85 if completed else 1.0,
                (ft.Colors.GREY_400 if completed else ft.Colors.GREY_200),
            ),
            decoration=(ft.TextDecoration.LINE_THROUGH if completed else None),
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
                            (ft.Colors.GREEN_400 if completed else ft.Colors.GREY_500),
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
        q = _truncate_display(d.get("query"), 120)
        return f'Knowledge base search: "{q}"' if q else "Knowledge base search"

    if act == "read_file":
        p = _truncate_display(d.get("path"), 200)
        return f"Read file: {p}" if p else "Read file"

    if act == "web_search":
        q = _truncate_display(d.get("query"), 120)
        return f'Web search: "{q}"' if q else "Web search"

    if act == "browse":
        u = _truncate_display(d.get("url"), 160)
        return f"Browse: {u}" if u else "Browse URL"

    if act == "github":
        pl = d.get("payload")

        ga = ""

        if isinstance(pl, dict):
            ga = str(pl.get("action") or "").strip()

        return f"GitHub: {_truncate_display(ga, 100)}" if ga else "GitHub request"

    if act == "read_code_block":
        uid = _truncate_display(d.get("id"), 80)
        return f"Request code block: {uid}" if uid else "Request code block"

    if act == "read_current_workflow":
        return "Full graph summary"

    if act == "grep":
        pat = _truncate_display(d.get("pattern"), 100)

        src = d.get("source")

        src_t = _truncate_display(src, 80) if src else ""

        if pat and src_t:
            return f'Grep "{pat}" in {src_t}'

        if pat:
            return f'Grep: "{pat}"'

        return "Grep"

    if act == "delegate_request":
        to = _truncate_display(
            d.get("delegate_to"),
            80,
        )

        return f"Delegate to: {to}" if to else "Delegate request"

    return act or "Request"


def streaming_assistant_opened_code_fence(text: str) -> bool:
    """True once the buffer has a complete opening fence line (triple backtick, optional lang, newline)."""
    return _OPEN_FENCE_LINE.search(text) is not None


def build_assistant_streaming_body(
    *,
    page: ft.Page,
    toast: Callable[[str], None],
    on_undo: Callable[[], None] | None,
    on_redo: Callable[[], None] | None,
    content: str,
    bubble_width: int | None,
) -> ft.Control:
    """Same rendering as a finished assistant bubble, for in-progress streamed content (incl. incomplete fences)."""
    return _render_assistant_content(
        page=page,
        toast=toast,
        on_undo=on_undo,
        on_redo=on_redo,
        applied=False,
        apply_failed=False,
        content=content,
        bubble_width=bubble_width,
    )


def normalize_message(
    m: Any,
    *,
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
) -> dict[str, Any] | None:
    """Ensure minimal fields exist and types are sane."""
    if not isinstance(m, dict):
        return None
    role = m.get("role")
    if role not in ("user", "assistant"):
        return None
    content = m.get("content")
    if not isinstance(content, str):
        content = "" if content is None else str(content)
    if not m.get("id"):
        m["id"] = new_id()
    if not m.get("ts"):
        m["ts"] = now_ts()
    m["role"] = role
    m["content"] = content
    return m


def render_messages(
    *,
    messages_col: ft.Column,
    chat_title_txt: ft.Text,
    history: list[dict[str, Any]],
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
    row_builder: Callable[[dict[str, Any]], ft.Row],
) -> None:
    messages_col.controls = [chat_title_txt]
    for m in history:
        nm = normalize_message(m, new_id=new_id, now_ts=now_ts)
        if nm is None:
            continue
        row = row_builder(nm)
        nm["_flet_row"] = row
        messages_col.controls.append(row)


def _query_display_lines(parsed: Any) -> list[str]:
    return [_query_action_summary_line(d) for d in _iter_action_dicts(parsed)]


def _extract_edit_action(
    parsed: Any,
) -> str | None:
    if not parsed:
        return None

    if isinstance(parsed, dict):
        action = parsed.get("action")

        if action not in (None, "no_edit"):
            return action

        edits = parsed.get("edits")

        if isinstance(edits, list):
            for e in edits:
                if isinstance(e, dict):
                    a = e.get("action")

                    if a not in (None, "no_edit"):
                        return a

    if isinstance(parsed, list):
        for e in parsed:
            if isinstance(e, dict):
                a = e.get("action")

                if a not in (None, "no_edit"):
                    return a

    return None


def _render_assistant_content(
    *,
    page: ft.Page,
    toast: Callable[[str], None],
    on_undo: Callable[[], None] | None,
    on_redo: Callable[[], None] | None,
    applied: bool,
    apply_failed: bool,
    content: str,
    bubble_width: int | None,
) -> ft.Control:

    segments = _split_fenced_blocks(content)

    controls: list[ft.Control] = []

    text_style = ft.TextStyle(
        size=12,
        color=ft.Colors.GREY_200,
    )

    border_color = ft.Colors.with_opacity(
        0.18,
        ft.Colors.WHITE,
    )

    for kind, lang, chunk in segments:
        if not chunk:
            continue

        if kind == "text":
            # delegate all plain text rendering (headers, tables, inline code, bold)
            controls.append(
                _build_assistant_plain_text_control(
                    _tex_arrows_to_unicode(chunk),
                    text_style=text_style,
                    bubble_width=bubble_width,
                )
            )
            continue

        code_body_raw = chunk

        parsed: Any = None
        action_type: str | None = None
        edit_count = 0

        try:
            parsed = json.loads(code_body_raw)
            action_type = _extract_edit_action(parsed)

        except Exception:
            pass

        if isinstance(parsed, dict):
            if parsed.get("action") not in (
                None,
                "no_edit",
            ):
                edit_count = 1

        elif isinstance(parsed, list):
            edit_count = sum(
                1
                for e in parsed
                if isinstance(e, dict) and e.get("action") not in (None, "no_edit")
            )

        failed = apply_failed and action_type not in (None, "no_edit")

        if _parsed_is_no_edit_only(parsed):
            controls.append(
                ft.Text(
                    "No changes were made to the flow.",
                    **_compact_meta_text_style(bubble_width=bubble_width),
                )
            )
            continue

        if _parsed_is_query_display_only(parsed):
            q_lines = _query_display_lines(parsed)

            controls.append(
                ft.Column(
                    controls=[
                        ft.Text(
                            line,
                            **_compact_meta_text_style(bubble_width=bubble_width),
                        )
                        for line in q_lines
                    ],
                    spacing=2,
                )
            )

            continue

        if _parsed_is_todo_display_only(parsed):
            todo_items = _iter_action_dicts(parsed)

            if _parsed_is_todo_mutators_only(parsed):
                m_lines = _todo_mutator_summary_lines(todo_items)

                show_success_icon = bool(applied and not failed)

                if m_lines:
                    if len(m_lines) == 1:
                        controls.append(
                            _compact_line_with_optional_success_icon(
                                m_lines[0],
                                bubble_width=bubble_width,
                                show_success_icon=show_success_icon,
                            )
                        )

                    else:
                        controls.append(
                            ft.Column(
                                controls=[
                                    _compact_line_with_optional_success_icon(
                                        line,
                                        bubble_width=bubble_width,
                                        show_success_icon=show_success_icon,
                                    )
                                    for line in m_lines
                                ],
                                spacing=2,
                            )
                        )

                continue

            final_list, twarnings, removed_flag = _simulate_todo_actions(todo_items)

            todo_controls = _build_todo_preview_controls(
                final_list,
                twarnings,
                list_explicitly_removed=removed_flag,
                bubble_width=bubble_width,
            )

            if todo_controls:
                controls.append(
                    ft.Column(
                        controls=todo_controls,
                        spacing=6,
                    )
                )

            continue

        header_text = ""

        if edit_count > 0:
            header_text = f"{edit_count} edit{'s' if edit_count != 1 else ''}"

        if failed:
            header_text += " (failed)"

        def _copy_code(
            e: ft.Event[ft.IconButton],
            _text: str = code_body_raw,
        ) -> None:

            async def _run() -> None:
                try:
                    await page.clipboard.set(_text)
                    toast("Copied!")
                except Exception:
                    pass

            page.run_task(_run)

        def _do_undo(
            e: ft.Event[ft.IconButton],
        ) -> None:
            if on_undo:
                try:
                    on_undo()
                except Exception:
                    pass

        def _do_redo(
            e: ft.Event[ft.IconButton],
        ) -> None:
            if on_redo:
                try:
                    on_redo()
                except Exception:
                    pass

        code_lang = (lang or "json").strip().lower()

        LINE_HEIGHT = 18
        COLLAPSED_LINES = 6

        lines = code_body_raw.splitlines()

        total_lines = len(lines)

        collapsed_height = COLLAPSED_LINES * LINE_HEIGHT

        full_height = (
            max(
                total_lines,
                1,
            )
            * LINE_HEIGHT
        )

        expanded_ref: list[bool] = [False]

        code_display_control, _, set_code_height = build_code_display(
            code_body_raw,
            language=code_lang,
            width=bubble_width,
            height=collapsed_height,
            page=page,
        )

        toggle_btn_ref: list[ft.IconButton | None] = [None]

        def _toggle_code_block(
            e: ft.Event[ft.IconButton],
        ) -> None:

            btn = toggle_btn_ref[0]

            if btn is None:
                return

            expanded_ref[0] = not expanded_ref[0]

            if expanded_ref[0]:
                set_code_height(full_height)
                btn.icon = ft.Icons.EXPAND_LESS
                btn.tooltip = "Show less"

            else:
                set_code_height(collapsed_height)
                btn.icon = ft.Icons.EXPAND_MORE
                btn.tooltip = "Show more"

            btn.update()
            page.update()

        _controls_style = ft.ButtonStyle(
            padding=2,
            shape=ft.RoundedRectangleBorder(radius=4),
        )

        toggle_btn = ft.IconButton(
            icon=ft.Icons.EXPAND_MORE,
            icon_size=16,
            style=_controls_style,
            tooltip="Show more",
            on_click=_toggle_code_block,
            padding=2,
            width=16,
            height=16,
            visible=total_lines > COLLAPSED_LINES,
        )

        toggle_btn_ref[0] = toggle_btn

        header_controls: list[ft.Control] = [
            ft.Container(expand=True),
            ft.Text(
                ("Applied" if applied and edit_count > 0 else ""),
                size=10,
                color=ft.Colors.GREEN_400,
                visible=applied and edit_count > 0,
            ),
            ft.Text(
                header_text,
                size=10,
                color=(ft.Colors.ORANGE_300 if failed else ft.Colors.GREY_400),
                visible=bool(header_text),
            ),
            ft.IconButton(
                icon=ft.Icons.UNDO,
                icon_size=14,
                width=18,
                height=18,
                style=_controls_style,
                tooltip="Undo",
                on_click=_do_undo,
                visible=edit_count > 0,
                disabled=on_undo is None,
            ),
            ft.IconButton(
                icon=ft.Icons.REDO,
                icon_size=14,
                width=18,
                height=18,
                style=_controls_style,
                tooltip="Redo",
                on_click=_do_redo,
                visible=edit_count > 0,
                disabled=on_redo is None,
            ),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY,
                icon_size=14,
                width=18,
                height=18,
                style=_controls_style,
                tooltip="Copy",
                on_click=_copy_code,
            ),
        ]

        body_controls: list[ft.Control] = [
            ft.Row(
                controls=cast(
                    list[ft.Control],
                    header_controls,
                ),
                spacing=10,
            ),
            code_display_control,
            ft.Row(
                controls=[
                    ft.Container(expand=True),
                    toggle_btn,
                ],
                alignment=ft.MainAxisAlignment.END,
                visible=(total_lines > COLLAPSED_LINES),
            ),
        ]

        controls.append(
            ft.Container(
                content=ft.Column(
                    controls=body_controls,
                    spacing=4,
                ),
                padding=ft.Padding.only(
                    left=2,
                    right=2,
                    top=8,
                    bottom=8,
                ),
                border=Border(
                    top=BorderSide(1, border_color),
                    right=BorderSide(1, border_color),
                    bottom=BorderSide(1, border_color),
                    left=BorderSide(1, border_color),
                ),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(
                    0.02,
                    ft.Colors.WHITE,
                ),
            )
        )

    if not controls:
        return _build_assistant_plain_text_control(
            _tex_arrows_to_unicode(content),
            text_style=text_style,
            bubble_width=bubble_width,
        )

    return ft.Column(
        controls=controls,
        spacing=6,
    )


def build_message_row(
    *,
    page: ft.Page,
    msg: dict[str, Any],
    persist: Callable[[], None],
    toast: Callable[[str], None],
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
    bubble_width: int | None = None,
) -> ft.Row:

    role = msg.get("role")

    content = str(msg.get("content") or "")

    is_user = role == "user"

    row_align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START

    if is_user:
        bubble_content: ft.Control = ft.Text(
            content,
            color=ft.Colors.GREY_200,
            size=12,
            selectable=True,
            no_wrap=False,
            width=bubble_width,
        )

    else:
        # Derive applied / apply_failed from the stored workflow metadata so that
        # status badges ("Applied", undo/redo, etc.) survive page reload and the
        # smooth-inline row promotion in _append.
        _wf = msg.get("workflow_response") or {}
        _result_kind = _wf.get("result_kind") or ""
        _msg_applied = _result_kind == "applied"
        _msg_apply_failed = _result_kind == "apply_failed"
        bubble_content = _render_assistant_content(
            page=page,
            toast=toast,
            on_undo=on_undo,
            on_redo=on_redo,
            applied=_msg_applied,
            apply_failed=_msg_apply_failed,
            content=content,
            bubble_width=bubble_width,
        )

    bubble = ft.Container(
        content=bubble_content,
        padding=ft.Padding.symmetric(
            horizontal=10,
            vertical=6,
        ),
        border_radius=6,
        bgcolor=(
            ft.Colors.with_opacity(
                0.10,
                ft.Colors.WHITE,
            )
            if is_user
            else ft.Colors.TRANSPARENT
        ),
        width=bubble_width if bubble_width is not None else None,
        expand=(bubble_width is None),
    )

    row_controls: list[ft.Control]

    if is_user:
        if bubble_width is None:
            row_controls = [
                ft.Container(width=12),  # fixed gutter on left for user messages
                bubble,
            ]
        else:
            row_controls = [
                ft.Container(expand=True),
                bubble,
            ]
    else:
        if bubble_width is None:
            row_controls = [
                bubble,
                ft.Container(width=12),  # fixed gutter on right for assistant messages
            ]
        else:
            row_controls = [
                bubble,
                ft.Container(expand=True),
            ]

    return ft.Row(
        controls=row_controls,
        alignment=row_align,
    )


__all__ = [
    "build_assistant_streaming_body",
    "build_message_row",
    "render_messages",
    "streaming_assistant_opened_code_fence",
]
