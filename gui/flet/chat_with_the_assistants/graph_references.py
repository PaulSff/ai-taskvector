from __future__ import annotations

from typing import Any, Callable

import flet as ft


class GraphReferencesController:
    """Manages pending graph/code refs, chip UI, and prompt formatting."""

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
        self.row = ft.Row(spacing=6, wrap=True, visible=False)

    def clear(self) -> None:
        self._refs.clear()
        self._sync_chips()

    def add_unit(self, unit_id: str) -> None:
        uid = (unit_id or "").strip()
        if not uid:
            return
        for r in self._refs:
            if r.get("kind") == "unit" and r.get("unit_id") == uid:
                self._toast("Node already in chat context")
                return
        label, unit_type = self._resolve_unit_meta(uid)
        self._refs.append(
            {"kind": "unit", "unit_id": uid, "label": label, "unit_type": unit_type}
        )
        self._sync_chips()
        self._toast(f"Added node to chat: {label}")

    def add_code(self, *, snippet: str, start: int, end: int) -> None:
        if not (snippet or "").strip():
            return
        self._refs.append(
            {"kind": "code", "snippet": snippet, "start": int(start), "end": int(end)}
        )
        self._sync_chips()
        self._toast("Added JSON selection to chat")

    def format_for_prompt(self) -> str:
        lines: list[str] = []
        for r in self._refs:
            if r.get("kind") == "unit":
                uid = r.get("unit_id", "")
                label = r.get("label", "")
                ut = r.get("unit_type", "")
                lines.append(f"[Graph node: {uid} - {label} (type: {ut})]")
            elif r.get("kind") == "code":
                sn = (r.get("snippet") or "").strip()
                if len(sn) > 1800:
                    sn = sn[:1797] + "..."
                lines.append(
                    f"[Workflow JSON selection (chars {r.get('start')}-{r.get('end')}):]\n{sn}"
                )
        return "\n".join(lines).strip()

    def _remove_ref_by_rid(self, rid: str) -> None:
        self._refs[:] = [r for r in self._refs if str(r.get("_rid", "")) != rid]
        self._sync_chips()

    def _sync_chips(self) -> None:
        self.row.controls.clear()
        for r in self._refs:
            if not r.get("_rid"):
                r["_rid"] = self._new_id()
            rid = str(r.get("_rid"))
            if r.get("kind") == "unit":
                txt = f"Node: {r.get('label', r.get('unit_id', '?'))}"
            elif r.get("kind") == "code":
                txt = f"JSON {r.get('start', '?')}-{r.get('end', '?')}"
            else:
                txt = "Ref"

            def _remove_chip(_e: ft.ControlEvent, _rid: str = rid) -> None:
                self._remove_ref_by_rid(_rid)

            self.row.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(txt, size=10, color=ft.Colors.GREY_300),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                icon_size=12,
                                tooltip="Remove",
                                on_click=_remove_chip,
                                padding=0,
                                style=ft.ButtonStyle(padding=0),
                            ),
                        ],
                        spacing=0,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    border_radius=6,
                    border=ft.border.all(1, ft.Colors.GREY_700),
                    bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                )
            )
        self.row.visible = bool(self.row.controls)
        try:
            self.row.update()
        except Exception:
            pass
