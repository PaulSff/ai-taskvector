from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import flet as ft
from flet import Control


class GraphReferencesController:
    """Manage pending graph/code/file references and chip UI."""

    def __init__(
        self,
        *,
        new_id: Callable[[], str],
        toast: Callable[[str], None],
        resolve_unit_meta: Callable[[str], tuple[str, str]],
    ) -> None:
        self._new_id = new_id
        self._toast = toast
        self._resolve_unit_meta = resolve_unit_meta

        self._refs: list[dict[str, Any]] = []

        self.row = ft.Row(
            controls=[],
            spacing=6,
            wrap=True,
            visible=False,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self._refs.clear()
        self._sync_chips(apply_update=True)

    def clear_quiet(self) -> None:
        """Clear refs without calling row.update()."""
        self._refs.clear()
        self._sync_chips(apply_update=False)

    def add_unit(self, unit_id: str) -> None:
        uid = (unit_id or "").strip()

        if not uid:
            return

        for ref in self._refs:
            if ref.get("kind") == "unit" and ref.get("unit_id") == uid:
                self._toast("Node already in chat context")
                return

        label, unit_type = self._resolve_unit_meta(uid)

        self._refs.append(
            {
                "kind": "unit",
                "unit_id": uid,
                "label": label,
                "unit_type": unit_type,
            }
        )

        self._sync_chips()
        self._toast(f"Added node to chat: {label}")

    def add_code(self, *, snippet: str, start: int, end: int) -> None:
        cleaned = (snippet or "").strip()

        if not cleaned:
            return

        self._refs.append(
            {
                "kind": "code",
                "snippet": cleaned,
                "start": int(start),
                "end": int(end),
            }
        )

        self._sync_chips()
        self._toast("Added JSON selection to chat")

    def add_file_path(self, path: str) -> None:
        cleaned = (path or "").strip()

        if not cleaned:
            return

        for ref in self._refs:
            if ref.get("kind") == "file_path" and ref.get("path") == cleaned:
                self._toast("Path already in chat context")
                return

        self._refs.append(
            {
                "kind": "file_path",
                "path": cleaned,
            }
        )

        self._sync_chips()
        self._toast(f"Added file to chat: {Path(cleaned).name}")

    def format_for_prompt(self) -> str:
        lines: list[str] = []

        for ref in self._refs:
            kind = ref.get("kind")

            if kind == "unit":
                uid = ref.get("unit_id", "")
                label = ref.get("label", "")
                unit_type = ref.get("unit_type", "")

                lines.append(f"[Graph node: {uid} - {label} (type: {unit_type})]")

            elif kind == "code":
                snippet = (ref.get("snippet") or "").strip()

                if len(snippet) > 1800:
                    snippet = snippet[:1797] + "..."

                lines.append(
                    f"[Workflow JSON selection "
                    f"(chars {ref.get('start')}-{ref.get('end')}):]\n"
                    f"{snippet}"
                )

            elif kind == "file_path":
                file_path = (ref.get("path") or "").strip()

                if file_path:
                    lines.append(f"[File path (mydata / context): {file_path}]")

        return "\n".join(lines).strip()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _remove_ref_by_rid(self, rid: str) -> None:
        self._refs[:] = [ref for ref in self._refs if str(ref.get("_rid", "")) != rid]

        self._sync_chips(apply_update=True)

    def _sync_chips(self, apply_update: bool = True) -> None:
        self.row.controls.clear()

        for ref in self._refs:
            if not ref.get("_rid"):
                ref["_rid"] = self._new_id()

            rid = str(ref.get("_rid"))

            chip_text: str
            chip_tooltip: str | None = None

            kind = ref.get("kind")

            if kind == "unit":
                chip_text = f"Node: {ref.get('label', ref.get('unit_id', '?'))}"

            elif kind == "code":
                chip_text = f"JSON {ref.get('start', '?')}-{ref.get('end', '?')}"

            elif kind == "file_path":
                file_path = (ref.get("path") or "").strip()

                filename = Path(file_path).name if file_path else "?"

                chip_text = (
                    f"File: {filename}"
                    if len(filename) <= 36
                    else f"File: …{filename[-32:]}"
                )

                chip_tooltip = file_path or None

            else:
                chip_text = "Ref"

            def _remove_chip(
                e: Any,
                _rid: str = rid,
            ) -> None:
                self._remove_ref_by_rid(_rid)

            # Explicitly typed as list[Control]
            chip_controls: list[Control] = [
                ft.Text(
                    chip_text,
                    size=10,
                    color=ft.Colors.GREY_300,
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_size=12,
                    tooltip="Remove",
                    on_click=_remove_chip,
                    padding=0,
                    style=ft.ButtonStyle(
                        padding=0,
                    ),
                ),
            ]

            chip = ft.Container(
                tooltip=chip_tooltip,
                padding=ft.Padding.symmetric(
                    horizontal=6,
                    vertical=2,
                ),
                border_radius=6,
                border=ft.Border(
                    top=ft.BorderSide(1, ft.Colors.GREY_700),
                    right=ft.BorderSide(1, ft.Colors.GREY_700),
                    bottom=ft.BorderSide(1, ft.Colors.GREY_700),
                    left=ft.BorderSide(1, ft.Colors.GREY_700),
                ),
                bgcolor=ft.Colors.with_opacity(
                    0.06,
                    ft.Colors.WHITE,
                ),
                content=ft.Row(
                    controls=chip_controls,
                    spacing=0,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

            self.row.controls.append(chip)

        self.row.visible = bool(self.row.controls)

        if apply_update:
            try:
                self.row.update()
            except RuntimeError:
                pass
