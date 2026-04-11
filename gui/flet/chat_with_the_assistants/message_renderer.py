from __future__ import annotations

import re
import json
from typing import Any, Callable
import flet as ft

from gui.flet.utils.code_editor import build_code_display

from core.graph.todo_list import (
    add_task as _todo_add_task,
    ensure_todo_list as _todo_ensure_list,
    mark_completed as _todo_mark_completed,
    remove_task as _todo_remove_task,
)

# Regex for fenced code blocks (```lang\n...\```)
_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z0-9_+-]+)?\n(?P<body>[\s\S]*?)```", re.MULTILINE)
# Opening fence line (must include newline after optional lang) for streaming / partial buffers
_OPEN_FENCE_LINE = re.compile(r"```([A-Za-z0-9_+-]+)?\n")
# Closing fence on its own line (markdown-style)
_CLOSE_FENCE_LINE = re.compile(r"(?m)^```\s*$")

# Markdown-style bold outside fenced blocks: **title** → bold span (non-greedy; multiline allowed)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _assistant_text_segments_with_bold(chunk: str) -> list[tuple[str, bool]]:
    """Split plain text into (fragment, is_bold) using **...** markers."""
    if not chunk:
        return []
    parts: list[tuple[str, bool]] = []
    last = 0
    for m in _MARKDOWN_BOLD_RE.finditer(chunk):
        if m.start() > last:
            parts.append((chunk[last : m.start()], False))
        parts.append((m.group(1), True))
        last = m.end()
    if last < len(chunk):
        parts.append((chunk[last:], False))
    return parts if parts else [(chunk, False)]


def _text_style_bold_variant(base: ft.TextStyle) -> ft.TextStyle:
    """Same as base with heavier weight for **...** spans."""
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
    """Plain assistant text segment with **bold** rendered as bold spans."""
    segs = _assistant_text_segments_with_bold(chunk)
    if len(segs) == 1 and not segs[0][1]:
        return ft.Text(
            segs[0][0],
            style=text_style,
            selectable=True,
            no_wrap=False,
            width=bubble_width if bubble_width is not None else None,
        )
    spans: list[ft.TextSpan] = []
    for fragment, is_bold in segs:
        if fragment == "":
            continue
        st = _text_style_bold_variant(text_style) if is_bold else text_style
        spans.append(ft.TextSpan(fragment, style=st))
    if not spans:
        return ft.Text(
            chunk,
            style=text_style,
            selectable=True,
            no_wrap=False,
            width=bubble_width if bubble_width is not None else None,
        )
    return ft.Text(
        spans=spans,
        selectable=True,
        no_wrap=False,
        width=bubble_width if bubble_width is not None else None,
    )


def _split_fenced_blocks(text: str) -> list[tuple[str, str | None, str]]:
    """Split text into ("text", None, chunk) and ("code", lang, body) segments.

    If the string ends with an opened fence (```lang?\\n) but no closing ``` line yet,
    the tail after that opening line is emitted as a ("code", lang, body) segment so the
    code editor can show partial JSON while the model is still generating.
    """
    parts: list[tuple[str, str | None, str]] = []
    last = 0
    for m in _FENCE_RE.finditer(text):
        if m.start() > last:
            parts.append(("text", None, text[last:m.start()]))
        lang = m.group("lang") or None
        body = m.group("body") or ""
        parts.append(("code", lang, body))
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
        # Tail contains a line that closes the fence; full _FENCE_RE should normally match —
        # if not (e.g. odd whitespace), keep as plain text to avoid splitting wrong.
        parts.append(("text", None, tail))
        return parts

    prefix = tail[: last_open.start()]
    if prefix:
        parts.append(("text", None, prefix))
    parts.append(("code", last_open.group(1) or None, body))
    return parts


def _format_action_block(parsed: dict[str, Any] | None, raw: str) -> str:
    """Convert parsed action JSON into readable text. Return raw if no action."""
    if not isinstance(parsed, dict):
        return raw
    action = parsed.get("action")
    if action == "no_edit":
        reason = parsed.get("reason", "No reason provided")
        return f"No edits were made. Reason: {reason}"
    return raw


def _parsed_is_no_edit_only(parsed: Any) -> bool:
    """True when the fenced JSON is only no_edit (chat renders that as a single plain line, not a code block)."""
    if isinstance(parsed, dict):
        if parsed.get("action") == "no_edit":
            return True
        edits = parsed.get("edits")
        if isinstance(edits, list) and len(edits) > 0:
            return all(isinstance(e, dict) and e.get("action") == "no_edit" for e in edits)
        return False
    if isinstance(parsed, list):
        if not parsed:
            return False
        return all(isinstance(e, dict) and e.get("action") == "no_edit" for e in parsed)
    return False


# Side-channel actions: no graph edit payload to inspect in a code editor; show compact summary lines.
_QUERY_DISPLAY_ACTIONS = frozenset({
    "search",
    "read_file",
    "web_search",
    "browse",
    "github",
    "read_code_block",
    "grep",
})

_TODO_DISPLAY_ACTIONS = frozenset({
    "add_todo_list",
    "remove_todo_list",
    "add_task",
    "remove_task",
    "mark_completed",
})

# Mutations that assume tasks already exist on the graph (no add_task in block → checklist sim is misleading).
_TODO_MUTATOR_ONLY_ACTIONS = frozenset({
    "mark_completed",
    "remove_task",
    "remove_todo_list",
})


def _iter_action_dicts(parsed: Any) -> list[dict[str, Any]]:
    """Flatten to dicts that carry an action (single edit, edits[], or list of edits)."""
    if isinstance(parsed, dict):
        edits = parsed.get("edits")
        if isinstance(edits, list) and len(edits) > 0:
            return [e for e in edits if isinstance(e, dict) and e.get("action")]
        if parsed.get("action") is not None:
            return [parsed]
        return []
    if isinstance(parsed, list):
        return [e for e in parsed if isinstance(e, dict) and e.get("action")]
    return []


def _compact_meta_text_style(*, bubble_width: int | None) -> dict[str, Any]:
    return {
        "size": 11,
        "color": ft.Colors.with_opacity(0.85, ft.Colors.GREY_400),
        "selectable": True,
        "no_wrap": False,
        "width": bubble_width,
    }


def _compact_line_with_optional_success_icon(
    line: str,
    *,
    bubble_width: int | None,
    show_success_icon: bool,
) -> ft.Control:
    """Compact summary line with optional tiny leading success check icon."""
    if not show_success_icon:
        return ft.Text(line, **_compact_meta_text_style(bubble_width=bubble_width))
    return ft.Row(
        [
            ft.Icon(
                ft.Icons.CHECK_CIRCLE,
                size=12,
                color=ft.Colors.with_opacity(0.95, ft.Colors.GREEN_400),
            ),
            ft.Text(line, **_compact_meta_text_style(bubble_width=bubble_width)),
        ],
        spacing=5,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        width=bubble_width,
    )


def _parsed_is_query_display_only(parsed: Any) -> bool:
    """True when every action is search/read/query style (no code-editor block)."""
    items = _iter_action_dicts(parsed)
    if not items:
        return False
    return all((e.get("action") or "") in _QUERY_DISPLAY_ACTIONS for e in items)


def _parsed_is_todo_display_only(parsed: Any) -> bool:
    """True when every action is todo-list only (render as checklist preview, not code editor)."""
    items = _iter_action_dicts(parsed)
    if not items:
        return False
    return all((e.get("action") or "") in _TODO_DISPLAY_ACTIONS for e in items)


def _parsed_is_todo_mutators_only(parsed: Any) -> bool:
    """True when block only marks/removes tasks (simulated checklist would start empty and confuse)."""
    items = _iter_action_dicts(parsed)
    if not items:
        return False
    return all((e.get("action") or "") in _TODO_MUTATOR_ONLY_ACTIONS for e in items)


def _todo_mutator_summary_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for d in items:
        act = (d.get("action") or "").strip()
        if act == "mark_completed":
            tid = _truncate_display(d.get("task_id"), 100)
            lines.append(f"Mark task complete: {tid}" if tid else "Mark task complete")
        elif act == "remove_task":
            tid = _truncate_display(d.get("task_id"), 100)
            lines.append(f"Remove task: {tid}" if tid else "Remove task")
        elif act == "remove_todo_list":
            lines.append("Remove todo list")
        else:
            lines.append(act or "Todo update")
    return lines


def _simulate_todo_actions(
    items: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str], bool]:
    """
    Apply todo actions in order (same semantics as graph apply).
    Returns (final todo_list or None, warnings, list_explicitly_removed).
    On per-step ValueError, append warning and leave state unchanged for that step.
    """
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
                    todo_list = {**todo_list, "title": str(title).strip()}
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
                todo_list = _todo_add_task(todo_list, str(text).strip(), task_id=tid_s or None)
            elif act == "remove_task":
                tid = d.get("task_id")
                if not tid or not str(tid).strip():
                    raise ValueError("remove_task: missing task_id")
                todo_list = _todo_ensure_list(todo_list)
                todo_list = _todo_remove_task(todo_list, str(tid).strip())
            elif act == "mark_completed":
                tid = d.get("task_id")
                if not tid or not str(tid).strip():
                    raise ValueError("mark_completed: missing task_id")
                todo_list = _todo_ensure_list(todo_list)
                completed = d.get("completed", True)
                if isinstance(completed, str):
                    completed = completed.strip().lower() in ("1", "true", "yes")
                todo_list = _todo_mark_completed(
                    todo_list, str(tid).strip(), completed=bool(completed)
                )
        except ValueError as e:
            warnings.append(str(e))
    return todo_list, warnings, list_explicitly_removed


def _build_todo_preview_controls(
    todo_list: dict[str, Any] | None,
    warnings: list[str],
    *,
    list_explicitly_removed: bool,
    bubble_width: int | None,
) -> list[ft.Control]:
    """Read-only todo preview rows (icons + text), plus optional warnings."""
    out: list[ft.Control] = []
    for w in warnings:
        out.append(
            ft.Text(
                f"⚠ {w}",
                size=10,
                color=ft.Colors.with_opacity(0.9, ft.Colors.AMBER_400),
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
                    **_compact_meta_text_style(bubble_width=bubble_width),
                )
            )
        elif warnings:
            out.append(
                ft.Text(
                    "Todo list preview unavailable (fix errors above).",
                    **_compact_meta_text_style(bubble_width=bubble_width),
                )
            )
        else:
            out.append(
                ft.Text(
                    "No todo list.",
                    **_compact_meta_text_style(bubble_width=bubble_width),
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
                **_compact_meta_text_style(bubble_width=bubble_width),
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
                ft.Colors.GREY_400 if completed else ft.Colors.GREY_200,
            ),
            decoration=ft.TextDecoration.LINE_THROUGH if completed else None,
        )
        out.append(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_BOX_ROUNDED
                        if completed
                        else ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED,
                        size=20,
                        color=ft.Colors.with_opacity(
                            0.95,
                            ft.Colors.GREEN_400 if completed else ft.Colors.GREY_500,
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


def _truncate_display(s: Any, max_len: int = 140) -> str:
    t = "" if s is None else str(s).strip().replace("\n", " ")
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _query_action_summary_line(d: dict[str, Any]) -> str:
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
    if act == "grep":
        pat = _truncate_display(d.get("pattern"), 100)
        src = d.get("source")
        src_t = _truncate_display(src, 80) if src else ""
        if pat and src_t:
            return f'Grep "{pat}" in {src_t}'
        if pat:
            return f'Grep: "{pat}"'
        return "Grep"
    return act or "Request"


def _query_display_lines(parsed: Any) -> list[str]:
    return [_query_action_summary_line(d) for d in _iter_action_dicts(parsed)]


def _extract_edit_action(parsed: Any) -> str | None:
    """Return first non-no_edit action found in dict, list, or {'edits': [...]}."""
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
        return None
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
    """Render assistant content with fenced code blocks, edit counts, and failures."""
    segments = _split_fenced_blocks(content)
    controls: list[ft.Control] = []

    text_style = ft.TextStyle(size=12, color=ft.Colors.GREY_200)
    border_color = ft.Colors.with_opacity(0.18, ft.Colors.WHITE)

    for kind, lang, chunk in segments:
        if not chunk:
            continue

        if kind == "text":
            controls.append(
                _build_assistant_plain_text_control(
                    chunk,
                    text_style=text_style,
                    bubble_width=bubble_width,
                )
            )
            continue

        # --- Code block ---
        code_body_raw = chunk  # preserve all whitespace/newlines
        parsed: dict[str, Any] | list[dict[str, Any]] | None = None
        action_type: str | None = None
        edit_count = 0
        failed = False

        # Try single JSON object first
        try:
            parsed = json.loads(code_body_raw)
            action_type = _extract_edit_action(parsed)
        except Exception:
            # Fallback: multiple concatenated JSON
            objs: list[dict[str, Any]] = []
            decoder = json.JSONDecoder()
            idx = 0
            s = code_body_raw.strip()
            while idx < len(s):
                try:
                    obj, end = decoder.raw_decode(s, idx)
                    if isinstance(obj, dict):
                        objs.append(obj)
                    idx = end
                    while idx < len(s) and s[idx].isspace():
                        idx += 1
                except json.JSONDecodeError:
                    break
            if objs:
                parsed = objs
                action_type = _extract_edit_action(objs)

        # Count edits; failure comes from apply meta (LLM output has no success field)
        if isinstance(parsed, dict):
            if parsed.get("action") not in (None, "no_edit"):
                edit_count = 1
        elif isinstance(parsed, list):
            edit_count = sum(
                1
                for e in parsed
                if isinstance(e, dict) and e.get("action") not in (None, "no_edit")
            )
        failed = apply_failed and (action_type not in (None, "no_edit"))

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
            if q_lines:
                if len(q_lines) == 1:
                    controls.append(ft.Text(q_lines[0], **_compact_meta_text_style(bubble_width=bubble_width)))
                else:
                    controls.append(
                        ft.Column(
                            [
                                ft.Text(line, **_compact_meta_text_style(bubble_width=bubble_width))
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
                                [
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
                controls.append(ft.Column(todo_controls, spacing=6))
            continue

        # Format the code block
        code_body = _format_action_block(
            parsed if isinstance(parsed, dict) else (parsed[0] if parsed else None),
            code_body_raw
        )
        is_no_edit = action_type == "no_edit"
        is_edit_action = action_type not in (None, "no_edit")

        # Build header text for edits/failures
        header_text = ""
        if is_edit_action:
            if edit_count > 0:
                header_text = f"{edit_count} edit{'s' if edit_count != 1 else ''}"
            if failed:
                header_text += " (failed)" if header_text else "Failed"

        # --- Clipboard, undo, redo handlers ---
        def _copy_code(_e: ft.ControlEvent, _text: str = code_body) -> None:
            async def _run() -> None:
                try:
                    await page.clipboard.set(_text)
                    toast("Copied!")
                except Exception:
                    pass
            page.run_task(_run)

        def _do_undo(_e: ft.ControlEvent) -> None:
            if on_undo:
                try: on_undo()
                except Exception: pass

        def _do_redo(_e: ft.ControlEvent) -> None:
            if on_redo:
                try: on_redo()
                except Exception: pass

        # --- Code block body: syntax-highlighted, collapsible (first N lines + Show more/less) ---
        code_lang = (lang or "json").strip().lower()
        if code_lang in ("js", "javascript"):
            code_lang = "javascript"
        elif code_lang not in ("json", "python", "javascript"):
            code_lang = "json"
        # Collapse by clipping viewport height only — do not append "\n..." or truncate text inside
        # the syntax editor. Truncated or pseudo lines break JSON/Python pairing and trigger
        # flutter_code_editor "invalid foldable block" gutter markers (red crosses).
        LINE_HEIGHT = 18
        COLLAPSED_LINES = 6
        lines = code_body.splitlines()
        total_lines = len(lines)
        if total_lines <= COLLAPSED_LINES:
            editor_height = max(1, total_lines) * LINE_HEIGHT
            collapsed_height: int | None = None
            full_height: int | None = None
            show_toggle = False
        else:
            collapsed_height = COLLAPSED_LINES * LINE_HEIGHT
            full_height = total_lines * LINE_HEIGHT
            editor_height = collapsed_height
            show_toggle = True
        expanded_ref: list[bool] = [False]
        code_display_control, set_code_display, set_code_height = build_code_display(
            code_body,
            language=code_lang,
            width=bubble_width,
            height=editor_height,
            page=page,
        )
        toggle_btn_ref: list[ft.IconButton | None] = [None]

        def _toggle_code_block(_e: ft.ControlEvent) -> None:
            if not show_toggle or toggle_btn_ref[0] is None:
                return
            expanded_ref[0] = not expanded_ref[0]
            if expanded_ref[0]:
                set_code_height(full_height)
                toggle_btn_ref[0].icon = ft.Icons.EXPAND_LESS
                toggle_btn_ref[0].tooltip = "Show less"
            else:
                set_code_height(collapsed_height)
                toggle_btn_ref[0].icon = ft.Icons.EXPAND_MORE
                toggle_btn_ref[0].tooltip = "Show more"
            try:
                toggle_btn_ref[0].update()
                page.update()
            except Exception:
                pass

        toggle_btn = ft.IconButton(
            icon=ft.Icons.EXPAND_MORE,
            icon_size=16,
            tooltip="Show more",
            on_click=_toggle_code_block,
            padding=2,
            style=ft.ButtonStyle(padding=2),
            visible=show_toggle,
        )
        toggle_btn_ref[0] = toggle_btn
        # --- Container ---
        controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(expand=True),
                                ft.Text(
                                    "Applied" if (applied and is_edit_action) else "",
                                    size=10,
                                    color=ft.Colors.GREEN_400,
                                    visible=bool(applied and is_edit_action),
                                ),
                                ft.Text(
                                    header_text,
                                    size=10,
                                    color=ft.Colors.ORANGE_300 if failed else ft.Colors.GREY_400,
                                    visible=bool(header_text),
                                ),
                                ft.IconButton(icon=ft.Icons.UNDO, icon_size=14, tooltip="Undo", on_click=_do_undo, padding=0, style=ft.ButtonStyle(padding=0), visible=is_edit_action, disabled=(on_undo is None)),
                                ft.IconButton(icon=ft.Icons.REDO, icon_size=14, tooltip="Redo", on_click=_do_redo, padding=0, style=ft.ButtonStyle(padding=0), visible=is_edit_action, disabled=(on_redo is None)),
                                ft.IconButton(icon=ft.Icons.CONTENT_COPY, icon_size=14, tooltip="Copy", on_click=_copy_code, padding=0, style=ft.ButtonStyle(padding=0), visible=not is_no_edit),
                            ],
                            spacing=4,
                        ),
                        code_display_control,
                        ft.Row(
                            [ft.Container(expand=True), toggle_btn],
                            alignment=ft.MainAxisAlignment.END,
                            visible=show_toggle,
                        ),
                    ],
                    spacing=4,
                ),
                padding=ft.Padding.only(left=10, right=6, top=6, bottom=8),
                border=ft.border.all(1, border_color),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.WHITE),
            )
        )

    if not controls:
        return ft.Text(
            content,
            style=text_style,
            selectable=True,
            no_wrap=False,
            width=bubble_width if bubble_width is not None else None,
        )

    return ft.Column(controls, spacing=6)


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


def build_message_row(
    *,
    page: ft.Page,
    msg: dict[str, Any],
    persist: Callable[[], None],
    toast: Callable[[str], None],
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
    now_ts: Callable[[], str] | None = None,
    bubble_width: int | None = 420,
) -> ft.Row:
    role = msg.get("role")
    content = msg.get("content") or ""
    is_user = role == "user"
    row_align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
    text_color = ft.Colors.WHITE if is_user else ft.Colors.GREY_200

    bubble_is_expand = bubble_width is None
    bubble_content: ft.Control
    if is_user:
        bubble_content = ft.Text(
            str(content),
            color=text_color,
            size=12,
            selectable=True,
            no_wrap=False,
            width=bubble_width if bubble_width is not None else None,
        )
    else:
        apply_meta = msg.get("apply")
        applied = False
        apply_failed = False
        if isinstance(apply_meta, dict) and bool(apply_meta.get("attempted")):
            if apply_meta.get("success") is True:
                applied = True
            else:
                apply_failed = True
        bubble_content = _render_assistant_content(
            page=page,
            toast=toast,
            on_undo=on_undo,
            on_redo=on_redo,
            applied=applied,
            apply_failed=apply_failed,
            content=str(content),
            bubble_width=bubble_width,
        )

    bubble = ft.Container(
        content=bubble_content,
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
        if is_user
        else ft.Colors.TRANSPARENT,
        width=bubble_width if bubble_width is not None else None,
        expand=True if bubble_is_expand else None,
    )

    def _save_feedback(value: str) -> None:
        fb: dict[str, Any] = {"type": "thumb", "value": value}
        if now_ts is not None:
            fb["ts"] = now_ts()
        msg["feedback"] = fb
        persist()
        toast("Thanks for the feedback!")

    feedback_bar: ft.Control | None = None
    if not is_user:
        fb_value: str | None = None
        fb = msg.get("feedback")
        if isinstance(fb, dict):
            v = fb.get("value")
            if v in ("up", "down"):
                fb_value = v

        up_btn: ft.IconButton | None = None
        down_btn: ft.IconButton | None = None

        def _apply_feedback_ui(value: str | None) -> None:
            nonlocal up_btn, down_btn
            if up_btn is None or down_btn is None:
                return
            # Highlight the selected rating; keep the other neutral.
            up_btn.icon_color = ft.Colors.GREEN_400 if value == "up" else ft.Colors.GREY_500
            down_btn.icon_color = ft.Colors.RED_400 if value == "down" else ft.Colors.GREY_500
            try:
                up_btn.update()
                down_btn.update()
            except Exception:
                pass

        feedback_bar = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.THUMB_UP,
                        icon_size=16,
                        tooltip="Good answer",
                        on_click=lambda _e: (_save_feedback("up"), _apply_feedback_ui("up")),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.THUMB_DOWN,
                        icon_size=16,
                        tooltip="Bad answer",
                        on_click=lambda _e: (_save_feedback("down"), _apply_feedback_ui("down")),
                    ),
                ],
                spacing=0,
            ),
            width=bubble_width if bubble_width is not None else None,
            expand=True if bubble_is_expand else None,
            padding=ft.Padding.only(left=2, right=2, top=0, bottom=0),
        )
        # Capture refs so we can update colors on click and initial render.
        try:
            row = feedback_bar.content  # type: ignore[assignment]
            if isinstance(row, ft.Row) and len(row.controls) >= 2:
                if isinstance(row.controls[0], ft.IconButton):
                    up_btn = row.controls[0]
                if isinstance(row.controls[1], ft.IconButton):
                    down_btn = row.controls[1]
        except Exception:
            pass
        _apply_feedback_ui(fb_value)

    row_children: list[ft.Control]
    content_stack: ft.Control = bubble if feedback_bar is None else ft.Column([bubble, feedback_bar], spacing=0)
    if bubble_is_expand:
        # Ensure the bubble gets a real width constraint so Text wraps.
        pad = ft.Padding.only(left=12) if not is_user else None
        row_children = [ft.Container(expand=True, content=content_stack, padding=pad)]
    else:
        if is_user:
            row_children = [ft.Container(expand=True), content_stack]
        else:
            row_children = [content_stack, ft.Container(expand=True)]

    return ft.Row(row_children, alignment=row_align)


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

