"""
Constructor GUI: Flet + Canvas graph (desktop).
Run from repo root: python -m gui.flet.main
Or: flet run gui/flet/main.py
"""
import sys
import time
from pathlib import Path

import flet as ft

# Import flet-code-editor early so Flet registers the CodeEditor control (avoids "Unknown control: CodeEditor")
try:
    import flet_code_editor  # noqa: F401
except ImportError:
    pass

# Ensure FilePicker control is registered (avoids "Unknown control: FilePicker" on some Flet clients)
from flet.controls.services.file_picker import FilePicker  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui.flet.components.workflow.core_workflows import run_load_workflow, run_runtime_label
from gui.flet.components.rag_tab import build_rag_tab
from gui.flet.components.training_tab import build_training_tab
from gui.flet.components.settings import (
    build_settings_tab,
    get_workflow_project_name,
    get_workflow_save_dir,
    get_window_width,
    get_window_height,
    save_settings,
)
from gui.flet.components.workflow import build_workflow_tab
from gui.flet.components.workflow.dialogs.dialog_save_workflow import save_workflow_version
from gui.flet.chat_with_the_assistants.chat import build_assistants_chat_panel
from gui.flet.chat_with_the_assistants.rag_context import ensure_units_indexed_at_startup
from gui.flet.tools.keyboard_commands import create_keyboard_handler
from gui.flet.tools.ollama_runner import maybe_start_ollama
from gui.flet.tools.notifications import show_toast
from core.schemas.process_graph import ProcessGraph

# Panel layout
LEFT_PANEL_MIN = 80
LEFT_PANEL_MAX = 280
LEFT_PANEL_DEFAULT = 100
RIGHT_PANEL_MIN = 300
RIGHT_PANEL_MAX = 520
RIGHT_PANEL_DEFAULT = 320
RESIZE_GRIP_WIDTH = 4
COLLAPSED_PANEL_WIDTH = 20
RESIZE_UPDATE_INTERVAL_S = 1 / 10  # Throttle panel resize to ~10fps to avoid lag when graph is visible


def main(page: ft.Page) -> None:
    # Apply saved or default window size (default ~30% larger than 1200x800)
    page.window_width = get_window_width()
    page.window_height = get_window_height()
    page.update()

    # Persist window size on resize (throttled)
    _last_window_size_save: list[float] = [0.0]
    WINDOW_SIZE_SAVE_THROTTLE_S = 1.0

    def _save_window_size_on_resize(_e: ft.ControlEvent) -> None:
        now = time.perf_counter()
        if now - _last_window_size_save[0] < WINDOW_SIZE_SAVE_THROTTLE_S:
            return
        _last_window_size_save[0] = now
        w = getattr(page, "window_width", None)
        h = getattr(page, "window_height", None)
        if w is not None and h is not None and w > 0 and h > 0:
            try:
                save_settings(window_width=int(w), window_height=int(h))
            except Exception:
                pass

    page.on_resize = _save_window_size_on_resize

    def _node_red_tab_label(graph: ProcessGraph | None) -> str | None:
        """Try to read Node-RED tab label from origin metadata (only when runtime is node_red)."""
        if graph is None:
            return None
        label, _ = run_runtime_label(graph)
        if label != "node_red":
            return None
        try:
            if graph.origin and graph.origin.node_red and graph.origin.node_red.tabs:
                for t in graph.origin.node_red.tabs:
                    label = getattr(t, "label", None)
                    if isinstance(label, str) and label.strip():
                        return label.strip()
        except Exception:
            pass
        return None

    def _set_page_title(graph: ProcessGraph | None) -> None:
        project_name = get_workflow_project_name()
        tab_label = _node_red_tab_label(graph)
        if project_name and tab_label:
            page.title = f"{project_name} - {tab_label}"
        elif project_name:
            page.title = f"{project_name}"
        elif tab_label:
            page.title = f"{tab_label}"
        else:
            page.title = "RL Agent gym"
        try:
            page.update()
        except Exception:
            pass

    _set_page_title(None)
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    # Load the most recently modified workflow from the save folder; else start empty
    graph_ref: list[ProcessGraph | None] = [None]
    save_dir = get_workflow_save_dir()
    if save_dir.exists():
        json_files = list(save_dir.glob("*.json"))
        if json_files:
            latest = max(json_files, key=lambda p: p.stat().st_mtime)
            try:
                graph_dict, err = run_load_workflow(str(latest))
                if not err and graph_dict is not None:
                    graph_ref[0] = ProcessGraph.model_validate(graph_dict)
                elif err:
                    print(f"Could not load workflow {latest}: {err}")
            except Exception as e:
                print(f"Could not load workflow {latest}: {e}")
    _set_page_title(graph_ref[0])

    # Workflow tab (process graph + code view + dialogs)
    (
        process_tab_column,
        _set_graph_base,
        apply_from_assistant,
        get_recent_changes,
        workflow_undo,
        workflow_redo,
        show_console_with_run_output,
    ) = build_workflow_tab(page, graph_ref, show_toast, on_graph_changed=_set_page_title)

    def set_graph(graph: ProcessGraph | None) -> None:
        _set_graph_base(graph)
        _set_page_title(graph)

    # Placeholder tabs
    training_content = build_training_tab(page, graph_ref=graph_ref)
    rag_content = build_rag_tab(page, show_rag_preview=_dev_mode())
    settings_content = build_settings_tab(page)
    contents = [process_tab_column, training_content, rag_content, settings_content]
    content_col = ft.Column(controls=[contents[0]], expand=True)
    active_tab_idx: list[int] = [0]

    # Lightweight placeholder shown while resizing to avoid expensive repaints
    resize_placeholder = ft.Container(
        expand=True,
        bgcolor=ft.Colors.GREY_900,
        content=ft.Row(
            [ft.Text("Resizing…", size=12, color=ft.Colors.GREY_500)],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
    )
    resizing: list[bool] = [False]

    def do_save_and_toast() -> None:
        result = save_workflow_version(graph_ref[0])

        async def _toast() -> None:
            if result.reason == "saved":
                await show_toast(page, "Saved!")
            elif result.reason == "no_changes":
                await show_toast(page, "No changes to save")
            elif result.reason == "no_graph":
                await show_toast(page, "No workflow loaded")
            else:
                await show_toast(page, "Save failed")

        page.run_task(_toast)

    _prev_keyboard = getattr(page, "on_keyboard_event", None)

    def _undo_if_workflow() -> None:
        if active_tab_idx[0] == 0:
            workflow_undo()

    def _redo_if_workflow() -> None:
        if active_tab_idx[0] == 0:
            workflow_redo()

    on_keyboard = create_keyboard_handler(
        _prev_keyboard,
        on_save=do_save_and_toast,
        on_undo=_undo_if_workflow,
        on_redo=_redo_if_workflow,
    )

    def on_show_run_console_from_chat(run_output: dict) -> None:
        """Switch to Workflow tab and show console with run_workflow results (no re-run)."""
        if active_tab_idx[0] != 0:
            nav_rail.selected_index = 0
            content_col.controls = [contents[0]]
            active_tab_idx[0] = 0
            page.update()
        show_console_with_run_output(run_output, append_log_grep=True)

    # Right column: assistants chat panel
    chat_content = build_assistants_chat_panel(
        page,
        graph_ref=graph_ref,
        set_graph=set_graph,
        apply_from_assistant=apply_from_assistant,
        get_recent_changes=get_recent_changes,
        on_undo=_undo_if_workflow,
        on_redo=_redo_if_workflow,
        show_run_current_graph=_dev_mode(),
        on_show_run_console=on_show_run_console_from_chat,
    )

    def on_rail_change(e: ft.ControlEvent) -> None:
        idx = e.control.selected_index
        if idx is None or idx < 0:
            idx = 0
        if idx <= 2:
            nav_rail.selected_index = idx
            content_col.controls = [contents[idx]]
            active_tab_idx[0] = idx
        page.update()

    def on_settings_click(_e: ft.ControlEvent) -> None:
        content_col.controls = [contents[3]]
        active_tab_idx[0] = 3
        page.update()

    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=60,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.ACCOUNT_TREE, label="Flow"),
            ft.NavigationRailDestination(icon=ft.Icons.TUNE, label="Gym"),
            ft.NavigationRailDestination(icon=ft.Icons.FOLDER_OPEN, label="RAG"),
        ],
        on_change=on_rail_change,
    )

    settings_btn = ft.IconButton(
        icon=ft.Icons.SETTINGS,
        tooltip="Settings",
        on_click=on_settings_click,
    )

    # Panel state (lists so closures can mutate)
    left_visible: list[bool] = [True]
    right_visible: list[bool] = [True]
    left_width: list[float] = [LEFT_PANEL_DEFAULT]
    right_width: list[float] = [RIGHT_PANEL_DEFAULT]
    last_resize_update: list[float] = [0.0]  # throttle UI updates during resize

    def _resize_begin(_e: ft.ControlEvent) -> None:
        """Enter lightweight resize mode to reduce lag (esp. Workflow canvas)."""
        if resizing[0]:
            return
        resizing[0] = True
        # Only swap out the heavy Workflow tab during drag; other tabs are cheap.
        if active_tab_idx[0] in (0, 1, 2):
            content_col.controls = [resize_placeholder]
            content_col.update()

    def _resize_end() -> None:
        """Exit lightweight resize mode and restore active tab content."""
        if not resizing[0]:
            return
        resizing[0] = False
        # Restore currently active tab control
        idx = active_tab_idx[0]
        if 0 <= idx < len(contents):
            content_col.controls = [contents[idx]]
            content_col.update()

    def _resize_flush(_e: ft.ControlEvent) -> None:
        """Apply final layout when drag ends."""
        left_panel_container.width = left_width[0]
        right_panel_container.width = right_width[0]
        # Update only affected panels (avoid full page rebuild).
        left_panel_container.update()
        right_panel_container.update()
        _resize_end()

    # Resize grip (draggable vertical strip)
    def make_left_grip():
        grip = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=20,
            on_horizontal_drag_start=_resize_begin,
            on_horizontal_drag_update=lambda e: _resize_left(e),
            on_horizontal_drag_end=_resize_flush,
            content=ft.Container(
                width=RESIZE_GRIP_WIDTH,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )
        return grip

    # Border for right resize edge (static; no hover highlight)
    _right_edge_border = ft.Border.only(left=ft.BorderSide(0.4, ft.Colors.GREY_700))

    def make_right_grip():
        grip = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=20,
            on_horizontal_drag_start=_resize_begin,
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
            # Update only the left panel to reduce lag.
            left_panel_container.update()

    def _resize_right(e: ft.DragUpdateEvent) -> None:
        delta = e.local_delta.x or 0
        w = right_width[0] - delta  # drag left = shrink
        w = max(RIGHT_PANEL_MIN, min(RIGHT_PANEL_MAX, w))
        right_width[0] = w
        right_panel_container.width = w
        now = time.perf_counter()
        if now - last_resize_update[0] >= RESIZE_UPDATE_INTERVAL_S:
            last_resize_update[0] = now
            # Update only the right panel to reduce lag.
            right_panel_container.update()

    def toggle_left(_e: ft.ControlEvent) -> None:
        left_visible[0] = not left_visible[0]
        if left_visible[0]:
            left_panel_container.content = left_expanded_row
            left_panel_container.width = left_width[0]
        else:
            left_panel_container.content = left_collapsed_content
            left_panel_container.width = COLLAPSED_PANEL_WIDTH
        left_panel_container.update()
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

    # Shared chevron style for left/right collapse buttons
    _chevron_style = ft.ButtonStyle(
        padding=0,
        shape=ft.RoundedRectangleBorder(radius=4),
    )
    _chevron_props = dict(icon_size=12, style=_chevron_style, width=28, height=28)

    # Left: collapse arrow on left edge, then nav rail, then resize grip
    left_rail_column = ft.Column(
        [
            ft.Container(content=nav_rail, expand=True),
            ft.Container(content=settings_btn, padding=8),
        ],
        expand=True,
        spacing=0,
    )
    left_collapsed_content = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT,
                on_click=toggle_left,
                **_chevron_props,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )
    left_expanded_row = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT,
                on_click=toggle_left,
                **_chevron_props,
            ),
            left_rail_column,
            make_left_grip(),
        ],
        spacing=0,
    )
    left_panel_container = ft.Container(
        content=left_expanded_row,
        width=left_width[0],
    )

    # Right: collapse = arrow pointing right (hide panel); expand = arrow pointing left
    right_collapsed_content = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT,
                on_click=toggle_right,
                **_chevron_props,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )
    right_chat_wrapper = ft.Container(
        content=chat_content,
        padding=ft.Padding.only(left=12, top=12, bottom=12, right=4),
        expand=True,
    )
    right_edge_container = ft.Container(
        border=_right_edge_border,
        content=make_right_grip(),
    )
    right_expanded_row = ft.Row(
        [
            right_edge_container,
            right_chat_wrapper,
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT,
                on_click=toggle_right,
                **_chevron_props,
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

    # Index units/ READMEs into RAG at startup (background) and show toast when done
    async def _rag_startup() -> None:
        await ensure_units_indexed_at_startup(page)
    page.run_task(_rag_startup)

    # If "Start Ollama with app" is on, start ollama serve in background and show result
    async def _ollama_startup() -> None:
        import asyncio
        ok, msg = await asyncio.to_thread(maybe_start_ollama)
        if msg and not ok:
            await show_toast(page, f"Ollama: {msg}")
        elif msg and ok and "already" not in msg.lower():
            await show_toast(page, "Ollama started")
    page.run_task(_ollama_startup)


def _dev_mode() -> bool:
    """True when run with -dev or --dev (e.g. python -m gui.flet.main -dev)."""
    return "-dev" in sys.argv or "--dev" in sys.argv


if __name__ == "__main__":
    ft.run(main)
