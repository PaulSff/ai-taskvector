"""
Constructor GUI: Flet + Canvas graph (desktop).
Run from repo root: python -m gui.flet.main
Or: flet run gui/flet/main.py
"""
import json
import sys
import time
from pathlib import Path

import flet as ft

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from normalizer import load_process_graph_from_file

from gui.flet.dialog_add_link import open_add_link_dialog
from gui.flet.dialog_add_node import open_add_node_dialog
from gui.flet.dialog_common import dict_to_graph
from gui.flet.dialog_remove_link import open_remove_link_dialog
from gui.flet.graph_canvas import build_graph_canvas
from schemas.process_graph import ProcessGraph

# Panel layout
LEFT_PANEL_MIN = 80
LEFT_PANEL_MAX = 280
LEFT_PANEL_DEFAULT = 100
RIGHT_PANEL_MIN = 220
RIGHT_PANEL_MAX = 520
RIGHT_PANEL_DEFAULT = 320
RESIZE_GRIP_WIDTH = 6
COLLAPSED_PANEL_WIDTH = 28
RESIZE_UPDATE_INTERVAL_S = 1 / 10  # Throttle panel resize to ~10fps to avoid lag when graph is visible


def main(page: ft.Page) -> None:
    page.title = "RL Agent gym (Flet)"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    # Load example process graph for Process tab (mutable ref so we can add nodes/links)
    example_path = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph_ref: list[ProcessGraph | None] = [None]
    if example_path.exists():
        try:
            graph_ref[0] = load_process_graph_from_file(str(example_path), format="yaml")
        except Exception as e:
            print(f"Could not load example graph: {e}")

    def build_process_tab_content() -> ft.Control:
        if graph_ref[0] is not None:
            return build_graph_canvas(
                page,
                graph_ref[0],
                on_right_click=lambda: (
                    open_remove_link_dialog(page, graph_ref[0], on_graph_saved)
                    if graph_ref[0] is not None
                    else None
                ),
            )
        return ft.Column(
            [
                ft.Text("Process graph", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("No process graph loaded. Click + to add a node or load from file."),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    process_content = ft.Container(content=build_process_tab_content(), expand=True)

    def refresh_process_tab() -> None:
        process_content.content = build_process_tab_content()
        process_content.update()
        page.update()

    def on_graph_saved(new_graph: ProcessGraph) -> None:
        graph_ref[0] = new_graph
        refresh_process_tab()

    def build_code_view_content() -> ft.Control:
        """Build the inline code view (JSON editor + Back to graph / Apply)."""
        try:
            json_str = (
                json.dumps(graph_ref[0].model_dump(by_alias=True), indent=2)
                if graph_ref[0] is not None
                else "{}"
            )
        except Exception:
            json_str = "{}"

        code_text = ft.TextField(
            value=json_str,
            multiline=True,
            expand=True,
            text_style=ft.TextStyle(font_family="monospace", size=13),
            border=ft.InputBorder.NONE,
            content_padding=ft.Padding.all(12),
            cursor_color=ft.Colors.CYAN_200,
        )

        def back_to_graph(_e: ft.ControlEvent) -> None:
            show_graph_view()

        def apply_code(_e: ft.ControlEvent) -> None:
            try:
                text = code_text.value or ""
                data = json.loads(text)
                new_graph = dict_to_graph(data)
                graph_ref[0] = new_graph
            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
                page.update()
                return
            show_graph_view()

        async def copy_to_clipboard(_e: ft.ControlEvent) -> None:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                await page.clipboard.set(code_text.value or "")
            toast_content = ft.Container(
                content=ft.Text("Copied!", size=12, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.GREY_700,
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                border_radius=6,
            )
            # Position at top center: full-width bar at top, Row centers the toast
            top_bar = ft.Container(
                content=ft.Row(
                    [ft.Container(content=toast_content, padding=ft.padding.only(top=20))],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                left=0,
                right=0,
                top=0,
            )
            toast = ft.Stack(
                expand=True,
                controls=[top_bar],
            )
            page.overlay.append(toast)
            page.update()
            import asyncio
            await asyncio.sleep(1)
            page.overlay.remove(toast)
            page.update()

        return ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK,
                                tooltip="Back to graph",
                                on_click=back_to_graph,
                                icon_color=ft.Colors.PRIMARY,
                            ),
                            ft.TextButton(content="Apply", on_click=apply_code),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.COPY,
                                tooltip="Copy to clipboard",
                                on_click=copy_to_clipboard,
                                icon_color=ft.Colors.PRIMARY,
                            ),
                        ],
                        spacing=8,
                    ),
                    bgcolor=ft.Colors.GREY_900,
                    padding=8,
                ),
                ft.Container(
                    content=code_text,
                    expand=True,
                    bgcolor=ft.Colors.GREY_900,
                ),
            ],
            expand=True,
            spacing=0,
        )

    def open_add_node(_e: ft.ControlEvent) -> None:
        try:
            open_add_node_dialog(page, graph_ref[0], on_graph_saved)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    def open_link(_e: ft.ControlEvent) -> None:
        if graph_ref[0] is None:
            return
        try:
            open_add_link_dialog(page, graph_ref[0], on_graph_saved)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    def open_unlink(_e: ft.ControlEvent) -> None:
        if graph_ref[0] is None:
            return
        try:
            open_remove_link_dialog(page, graph_ref[0], on_graph_saved)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    code_view_container = ft.Container(
        expand=True,
        content=ft.Text("Code", color=ft.Colors.GREY_500),
        bgcolor=ft.Colors.GREY_900,
    )
    process_main_view = ft.Container(expand=True, content=process_content)

    ACTIVE_ICON_COLOR = ft.Colors.GREY_200
    INACTIVE_ICON_COLOR = ft.Colors.GREY_500

    def update_view_tab_icons(active: str) -> None:
        """Set icon color for Graph/Code tab buttons; active='graph' or 'code'."""
        graph_btn.icon_color = ACTIVE_ICON_COLOR if active == "graph" else INACTIVE_ICON_COLOR
        code_btn.icon_color = ACTIVE_ICON_COLOR if active == "code" else INACTIVE_ICON_COLOR
        graph_btn.update()
        code_btn.update()

    def show_graph_view() -> None:
        process_main_view.content = process_content
        refresh_process_tab()
        update_view_tab_icons("graph")
        process_main_view.update()
        page.update()

    def show_code_view_switch(_e: ft.ControlEvent) -> None:
        code_view_container.content = build_code_view_content()
        process_main_view.content = code_view_container
        update_view_tab_icons("code")
        process_main_view.update()
        page.update()

    def show_graph_view_switch(_e: ft.ControlEvent) -> None:
        show_graph_view()

    graph_btn = ft.IconButton(
        icon=ft.Icons.ACCOUNT_TREE,
        tooltip="Graph",
        on_click=show_graph_view_switch,
        icon_color=ACTIVE_ICON_COLOR,
    )
    code_btn = ft.IconButton(
        icon=ft.Icons.CODE,
        tooltip="Code",
        on_click=show_code_view_switch,
        icon_color=INACTIVE_ICON_COLOR,
    )

    process_toolbar = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(icon=ft.Icons.ADD, tooltip="Add node", on_click=open_add_node),
                ft.IconButton(icon=ft.Icons.LINK, tooltip="Add link", on_click=open_link),
                ft.IconButton(icon=ft.Icons.LINK_OFF, tooltip="Remove link", on_click=open_unlink),
                ft.Container(expand=True),  # spacer
                graph_btn,
                code_btn,
            ],
            spacing=4,
        ),
        bgcolor=ft.Colors.GREY_900,
        padding=8,
    )
    process_tab_column = ft.Column(
        [
            process_toolbar,
            process_main_view,
        ],
        expand=True,
        spacing=0,
    )

    # Placeholder tabs
    training_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("Training config", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Load / edit training YAML and hyperparameters (placeholder)."),
            ],
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=24,
        expand=True,
    )
    run_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("Run / Test", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Run training or test policy (placeholder)."),
            ],
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=24,
        expand=True,
    )
    contents = [process_tab_column, training_content, run_content]
    content_col = ft.Column(controls=[contents[0]], expand=True)

    # Right column: chat UI
    chat_messages = ft.Column(
        [ft.Text("Ask about workflows, training, or running the agent.", color=ft.Colors.GREY_500, size=12)],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=8,
    )
    chat_input = ft.TextField(
        hint_text="Message...",
        multiline=False,
        min_lines=1,
        max_lines=1,
        on_submit=lambda e: send_chat(e.control) if e.control.value.strip() else None,
    )

    def send_chat(field: ft.TextField) -> None:
        text = (field.value or "").strip()
        if not text:
            return
        field.value = ""
        field.update()
        # User message
        chat_messages.controls.append(
            ft.Row(
                [ft.Text(text, color=ft.Colors.WHITE, size=13)],
                alignment=ft.MainAxisAlignment.END,
            )
        )
        # Placeholder reply
        chat_messages.controls.append(
            ft.Row(
                [ft.Text("Assistant (placeholder): Reply not implemented yet.", color=ft.Colors.GREY_400, size=12)],
                alignment=ft.MainAxisAlignment.START,
            )
        )
        chat_messages.update()
        page.update()

    chat_content = ft.Column(
        [
            ft.Text("Assistant", size=16, weight=ft.FontWeight.BOLD),
            ft.Container(content=chat_messages, expand=True),
            ft.Row(
                [
                    chat_input,
                    ft.IconButton(icon=ft.Icons.SEND, on_click=lambda e: send_chat(chat_input)),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        ],
        expand=True,
        spacing=8,
    )

    def on_rail_change(e: ft.ControlEvent) -> None:
        idx = e.control.selected_index or 0
        nav_rail.selected_index = idx
        content_col.controls = [contents[idx]]
        page.update()

    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=60,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.ACCOUNT_TREE, label="Workflow"),
            ft.NavigationRailDestination(icon=ft.Icons.TUNE, label="Training"),
            ft.NavigationRailDestination(icon=ft.Icons.PLAY_ARROW, label="Run/Test"),
        ],
        on_change=on_rail_change,
    )

    # Panel state (lists so closures can mutate)
    right_visible: list[bool] = [True]
    left_width: list[float] = [LEFT_PANEL_DEFAULT]
    right_width: list[float] = [RIGHT_PANEL_DEFAULT]
    last_resize_update: list[float] = [0.0]  # throttle UI updates during resize

    def _resize_flush(_e: ft.ControlEvent) -> None:
        """Apply final layout when drag ends."""
        left_panel_container.width = left_width[0]
        right_panel_container.width = right_width[0]
        page.update()

    # Resize grip (draggable vertical strip)
    def make_left_grip():
        grip = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=20,
            on_horizontal_drag_update=lambda e: _resize_left(e),
            on_horizontal_drag_end=_resize_flush,
            content=ft.Container(
                width=RESIZE_GRIP_WIDTH,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )
        return grip

    # Border for right resize edge: normal and highlighted (when cursor is over grip)
    _right_edge_border = ft.Border.only(left=ft.BorderSide(0.4, ft.Colors.GREY_700))
    _right_edge_border_highlight = ft.Border.only(left=ft.BorderSide(2, ft.Colors.GREY_700))
    _right_edge_container_ref: list[ft.Container | None] = [None]

    def _highlight_right_edge(highlight: bool) -> None:
        if _right_edge_container_ref[0] is not None:
            _right_edge_container_ref[0].border = (
                _right_edge_border_highlight if highlight else _right_edge_border
            )
            page.update(_right_edge_container_ref[0])

    def make_right_grip():
        grip = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=20,
            on_horizontal_drag_update=lambda e: _resize_right(e),
            on_horizontal_drag_end=_resize_flush,
            on_enter=lambda _: _highlight_right_edge(True),
            on_exit=lambda _: _highlight_right_edge(False),
            content=ft.Container(
                width=RESIZE_GRIP_WIDTH,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )
        return grip

    def _resize_left(e: ft.DragUpdateEvent) -> None:
        delta = e.local_delta.x or 0
        w = left_width[0] + delta
        w = max(LEFT_PANEL_MIN, min(LEFT_PANEL_MAX, w))
        left_width[0] = w
        left_panel_container.width = w
        now = time.perf_counter()
        if now - last_resize_update[0] >= RESIZE_UPDATE_INTERVAL_S:
            last_resize_update[0] = now
            page.update(left_panel_container)

    def _resize_right(e: ft.DragUpdateEvent) -> None:
        delta = e.local_delta.x or 0
        w = right_width[0] - delta  # drag left = shrink
        w = max(RIGHT_PANEL_MIN, min(RIGHT_PANEL_MAX, w))
        right_width[0] = w
        right_panel_container.width = w
        now = time.perf_counter()
        if now - last_resize_update[0] >= RESIZE_UPDATE_INTERVAL_S:
            last_resize_update[0] = now
            page.update(right_panel_container)

    def toggle_right(_e: ft.ControlEvent) -> None:
        right_visible[0] = not right_visible[0]
        if right_visible[0]:
            right_panel_container.content = right_expanded_row
            right_panel_container.width = right_width[0]
        else:
            right_panel_container.content = right_collapsed_content
            right_panel_container.width = COLLAPSED_PANEL_WIDTH
        right_panel_container.update()
        page.update()

    # Left: nav rail + resize grip only (no hide/show)
    left_panel_container = ft.Container(
        content=ft.Row(
            [
                ft.Container(content=nav_rail, expand=True),
                make_left_grip(),
            ],
            spacing=0,
        ),
        width=left_width[0],
    )

    # Right: collapse = arrow pointing right (hide panel); expand = arrow pointing left
    right_collapsed_content = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT,
                icon_size=18,
                style=ft.ButtonStyle(padding=2, shape=ft.RoundedRectangleBorder(radius=4)),
                on_click=toggle_right,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )
    right_chat_wrapper = ft.Container(
        content=chat_content,
        padding=12,
        expand=True,
    )
    right_edge_container = ft.Container(
        border=_right_edge_border,
        content=make_right_grip(),
    )
    _right_edge_container_ref[0] = right_edge_container
    right_expanded_row = ft.Row(
        [
            right_edge_container,
            right_chat_wrapper,
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT,
                icon_size=18,
                style=ft.ButtonStyle(padding=2, shape=ft.RoundedRectangleBorder(radius=4)),
                on_click=toggle_right,
            ),
        ],
        spacing=0,
    )
    right_panel_container = ft.Container(
        content=right_expanded_row,
        width=right_width[0],
    )

    page.add(
        ft.Row(
            [
                left_panel_container,
                ft.VerticalDivider(width=1),
                content_col,
                right_panel_container,
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.run(main)
