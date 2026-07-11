from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import flet as ft

from core.schemas.process_graph import ProcessGraph
from gui.utils.code_editor import build_code_editor

OVERLAY_BG = ft.Colors.with_opacity(0.92, ft.Colors.BLACK)


def get_block_index_from_cursor(
    get_selection_range: Callable[[], tuple[int, int] | None],
    block_ranges: list[tuple[int, int, Any]],
    active_editor: list[str],
) -> Any | None:
    """Return the range tag (e.g. ``(\"code_blocks\", i)``) under the caret, if any."""
    if active_editor[0] != "json":
        return None
    try:
        rng = get_selection_range()
        if not rng:
            return None
        caret = min(rng)
        for start, end, idx in block_ranges:
            if start <= caret <= end:
                return idx
        return None
    except Exception:
        return None


def _resolve_comment(
    payload: dict[str, Any], comment_id: str, graph: ProcessGraph | None
) -> tuple[bool, str]:
    """Whether the comment exists and its current info text."""
    if payload.get("id") == comment_id:
        return True, str(payload.get("info") or "")
    comments = payload.get("comments")
    if isinstance(comments, list):
        for c in comments:
            if isinstance(c, dict) and c.get("id") == comment_id:
                return True, str(c.get("info") or "")
    if graph is not None:
        co = next((c for c in (graph.comments or []) if c.id == comment_id), None)
        if co is not None:
            return True, str(co.info or "")
    return False, ""


def _write_comment_info(payload: dict[str, Any], comment_id: str, text: str) -> bool:
    """Update comment ``info`` on the root comment dict or inside ``comments``."""
    if payload.get("id") == comment_id:
        payload["info"] = text
        return True
    clist = payload.setdefault("comments", [])
    if isinstance(clist, list):
        for c in clist:
            if isinstance(c, dict) and c.get("id") == comment_id:
                c["info"] = text
                return True
    return False


@dataclass(frozen=True)
class GraphJsonOverlayBundle:
    """Controls returned by :func:`create_graph_json_overlay`."""

    code_overlay: ft.Container
    """Semi-transparent layer with the block/comment editor."""
    active_editor: list[str]
    """Single-element list: ``"json"`` (main editor) or ``"block"`` (overlay)."""
    show_json_editor: Callable[[], None]
    """Hide overlay and show the main JSON editor (per ``hide_editor_when_overlay``)."""
    show_block_overlay: Callable[[], None]
    """Show overlay; optionally hide main editor."""
    close_overlay: Callable[[], None]
    """Clear overlay content and return to the main JSON editor."""
    open_code_editor: Callable[[int | tuple], None]
    """Open overlay for a code block index or range tag tuple."""


def create_graph_json_overlay(
    page: ft.Page,
    *,
    full_json_ref: list[dict[str, Any]],
    refresh_editor: Callable[[], None],
    editor_container: ft.Container,
    graph: ProcessGraph | None,
    hide_editor_when_overlay: bool,
) -> GraphJsonOverlayBundle:
    """
    Build overlay container and callbacks for editing ``code_blocks[].source``, comment ``info``,
    or root ``metadata`` string fields (``metadata_field`` ranges from the JSON formatter).

    ``full_json_ref`` is the mutable JSON dict shown in the main editor (same object that Apply saves).
    """
    code_overlay = ft.Container(visible=False, expand=True, bgcolor=OVERLAY_BG)
    active_editor: list[str] = ["json"]

    def show_json_editor() -> None:
        active_editor[0] = "json"
        code_overlay.visible = False
        code_overlay.content = None
        if hide_editor_when_overlay:
            editor_container.visible = True
        try:
            editor_container.update()
            code_overlay.update()
        except Exception:
            pass

    def show_block_overlay() -> None:
        active_editor[0] = "block"
        code_overlay.visible = True
        if hide_editor_when_overlay:
            editor_container.visible = False
        try:
            editor_container.update()
            code_overlay.update()
        except Exception:
            pass

    def close_overlay() -> None:
        code_overlay.content = None
        show_json_editor()

    def open_code_editor(block_index: int | tuple) -> None:
        payload = full_json_ref[0]
        if isinstance(block_index, int):
            block_index = ("code_blocks", block_index)

        comment_id_local: str | None = None
        metadata_field_local: str | None = None
        block: dict[str, Any] | None = None
        code_block_index: int | None = None

        # default language for non-code-block edits; markdown (not "text")
        lang: str = "md"
        source: str = ""

        if isinstance(block_index, tuple) and block_index[0] == "code_blocks":
            _, code_block_index = block_index
            blocks = payload.get("code_blocks")
            if not isinstance(blocks, list):
                return
            if not isinstance(code_block_index, int):
                return
            if code_block_index < 0 or code_block_index >= len(blocks):
                return
            block = blocks[code_block_index]
            if not isinstance(block, dict):
                return

            raw_lang = block.get("language", "python")
            lang = "python" if raw_lang is None else str(raw_lang)

            src = block.get("source", "")
            source = "" if src is None else str(src)

        elif isinstance(block_index, tuple) and block_index[0] in (
            "comment_info",
            "comment_obj",
        ):
            _, cid = block_index
            comment_id_local = cid
            ok, source = _resolve_comment(payload, cid, graph)
            if not ok:
                return
            lang = "md"

        elif isinstance(block_index, tuple) and block_index[0] == "metadata_field":
            _, field_key = block_index
            if not isinstance(field_key, str) or not field_key.strip():
                return
            metadata_field_local = field_key.strip()
            meta = payload.get("metadata")
            if not isinstance(meta, dict):
                source = ""
            else:
                raw = meta.get(metadata_field_local)
                source = "" if raw is None else str(raw)
            lang = "md"

        else:
            return

        def apply_code_block_source(text: str) -> None:
            if code_block_index is None:
                return
            blocks = payload.get("code_blocks", [])
            if (
                isinstance(blocks, list)
                and isinstance(code_block_index, int)
                and 0 <= code_block_index < len(blocks)
            ):
                blocks[code_block_index]["source"] = text

        def apply_comment(text: str) -> None:
            if comment_id_local:
                _write_comment_info(payload, comment_id_local, text)

        def apply_metadata_field(text: str) -> None:
            if not metadata_field_local:
                return
            meta = payload.setdefault("metadata", {})
            if not isinstance(meta, dict):
                payload["metadata"] = {metadata_field_local: text}
            else:
                meta[metadata_field_local] = text

        title: str
        if comment_id_local is not None:
            title = comment_id_local
        elif metadata_field_local is not None:
            title = f"metadata.{metadata_field_local}"
        elif block is not None:
            title = str(block.get("id", code_block_index))
        else:
            title = "block"

        # keep TextField fallback only for truly generic "text" mode
        if lang == "text":
            text_field = ft.TextField(value=source, multiline=True, expand=True)

            def block_get_value() -> str:
                return text_field.value or ""

            def apply_changes(_e=None) -> None:
                if comment_id_local is not None:
                    apply_comment(block_get_value())
                elif metadata_field_local is not None:
                    apply_metadata_field(block_get_value())
                else:
                    apply_code_block_source(block_get_value())
                refresh_editor()
                close_overlay()

            header = ft.Row(
                [
                    ft.Text(f"Editing: {title}"),
                    ft.IconButton(icon=ft.Icons.CHECK, on_click=apply_changes),
                    ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda _e: close_overlay()),
                ]
            )
            code_overlay.content = ft.Column(
                [header, text_field],
                expand=True,
            )
            show_block_overlay()
            return

        # use syntax-highlight editor for markdown (and other languages)
        block_editor, block_get_value, *_ = build_code_editor(
            code=source,
            expand=True,
            page=page,
            language=lang,
        )

        def apply_changes(_e=None) -> None:
            if comment_id_local is not None:
                apply_comment(block_get_value())
            elif metadata_field_local is not None:
                apply_metadata_field(block_get_value())
            else:
                apply_code_block_source(block_get_value())
            refresh_editor()
            close_overlay()

        header = ft.Row(
            [
                ft.Text(f"Editing: {title}"),
                ft.IconButton(icon=ft.Icons.CHECK, on_click=apply_changes),
                ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda _e: close_overlay()),
            ]
        )
        code_overlay.content = ft.Column(
            [header, block_editor],
            expand=True,
        )
        show_block_overlay()

    return GraphJsonOverlayBundle(
        code_overlay=code_overlay,
        active_editor=active_editor,
        show_json_editor=show_json_editor,
        show_block_overlay=show_block_overlay,
        close_overlay=close_overlay,
        open_code_editor=open_code_editor,
    )
