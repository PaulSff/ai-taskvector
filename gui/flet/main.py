"""
Constructor GUI: Flet + Canvas graph (desktop).
Run from repo root: python -m gui.flet.main
Or: flet run gui/flet/main.py
"""
import sys
import time
from pathlib import Path

import flet as ft

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from normalizer import load_process_graph_from_file

from gui.flet.graph_canvas import build_graph_canvas

# Panel layout
LEFT_PANEL_MIN = 80
LEFT_PANEL_MAX = 280
LEFT_PANEL_DEFAULT = 100
RIGHT_PANEL_MIN = 220
RIGHT_PANEL_MAX = 520
RIGHT_PANEL_DEFAULT = 320
RESIZE_GRIP_WIDTH = 6
COLLAPSED_PANEL_WIDTH = 28
RESIZE_UPDATE_INTERVAL_S = 1 / 24  # Throttle panel resize redraws to ~24fps to avoid lag with graph


def main(page: ft.Page) -> None:
    page.title = "RL Agent gym (Flet)"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    # Load example process graph for Process tab
    example_path = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = None
    if example_path.exists():
        try:
            graph = load_process_graph_from_file(str(example_path), format="yaml")
        except Exception as e:
            print(f"Could not load example graph: {e}")

    # Process tab: pure Flet Canvas + Node controls
    if graph is not None:
        process_content = ft.Container(content=build_graph_canvas(page, graph), expand=True)
    else:
        process_content = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Process graph", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text("No process graph loaded. Add config/examples/temperature_process.yaml or load from file."),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
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
    contents = [process_content, training_content, run_content]
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
        left_panel_container.update()
        right_panel_container.update()
        page.update()

    # Resize grip (draggable vertical strip)
    def make_left_grip():
        grip = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=5,
            on_horizontal_drag_update=lambda e: _resize_left(e),
            on_horizontal_drag_end=_resize_flush,
            content=ft.Container(
                width=RESIZE_GRIP_WIDTH,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )
        return grip

    def make_right_grip():
        grip = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=5,
            on_horizontal_drag_update=lambda e: _resize_right(e),
            on_horizontal_drag_end=_resize_flush,
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
            left_panel_container.update()
            page.update()

    def _resize_right(e: ft.DragUpdateEvent) -> None:
        delta = e.local_delta.x or 0
        w = right_width[0] - delta  # drag left = shrink
        w = max(RIGHT_PANEL_MIN, min(RIGHT_PANEL_MAX, w))
        right_width[0] = w
        right_panel_container.width = w
        now = time.perf_counter()
        if now - last_resize_update[0] >= RESIZE_UPDATE_INTERVAL_S:
            last_resize_update[0] = now
            right_panel_container.update()
            page.update()

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
    right_expanded_row = ft.Row(
        [
            make_right_grip(),
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
                ft.VerticalDivider(width=1),
                right_panel_container,
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.run(main)
