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

from gui.flet.components.settings import build_settings_tab, get_workflow_save_path
from gui.flet.components.workflow import build_workflow_tab
from gui.flet.tools.keyboard_commands import create_keyboard_handler
from gui.flet.tools.notifications import show_toast
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

    # Load example process graph for Workflow tab (mutable ref so workflow can add nodes/links)
    example_path = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph_ref: list[ProcessGraph | None] = [None]
    if example_path.exists():
        try:
            graph_ref[0] = load_process_graph_from_file(str(example_path), format="yaml")
        except Exception as e:
            print(f"Could not load example graph: {e}")

    # Workflow tab (process graph + code view + dialogs)
    process_tab_column = build_workflow_tab(page, graph_ref, show_toast)

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
    settings_content = build_settings_tab(page)
    contents = [process_tab_column, training_content, run_content, settings_content]
    content_col = ft.Column(controls=[contents[0]], expand=True)

    def save_workflow() -> bool:
        """Save current graph to path from settings. Returns True if saved, False if no graph or error."""
        graph = graph_ref[0]
        if graph is None:
            return False
        save_path = get_workflow_save_path()
        path = (REPO_ROOT / save_path) if not Path(save_path).is_absolute() else Path(save_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(graph.model_dump(by_alias=True), indent=2),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    def do_save_and_toast() -> None:
        if save_workflow():
            async def _toast_saved() -> None:
                await show_toast(page, "Saved!")

            page.run_task(_toast_saved)

    _prev_keyboard = getattr(page, "on_keyboard_event", None)
    on_keyboard = create_keyboard_handler(_prev_keyboard, on_save=do_save_and_toast)

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
        idx = e.control.selected_index
        if idx is None or idx < 0:
            idx = 0
        if idx <= 2:
            nav_rail.selected_index = idx
            content_col.controls = [contents[idx]]
        page.update()

    def on_settings_click(_e: ft.ControlEvent) -> None:
        content_col.controls = [contents[3]]
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
    settings_btn = ft.IconButton(
        icon=ft.Icons.SETTINGS,
        tooltip="Settings",
        on_click=on_settings_click,
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

    # Left: nav rail, Settings button at bottom, then resize grip
    left_rail_column = ft.Column(
        [
            ft.Container(content=nav_rail, expand=True),
            ft.Container(content=settings_btn, padding=8),
        ],
        expand=True,
        spacing=0,
    )
    left_panel_container = ft.Container(
        content=ft.Row(
            [
                left_rail_column,
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
            spacing=0,
        )
    )
    page.on_keyboard_event = on_keyboard


if __name__ == "__main__":
    ft.run(main)
