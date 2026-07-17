"""
Constructor GUI: Flet + Canvas graph (desktop).
Run from repo root: python -m gui.main
Or: flet run gui/main.py
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, List

import flet as ft
from flet import (
    ControlEventHandler,
    DragEndEvent,
    DragStartEvent,
    DragUpdateEvent,
    Event,
    Page,
)

from core.schemas.process_graph import ProcessGraph
from gui.chat.chat import CHAT_GRAPH_DRAG_GROUP, build_agents_chat_panel
from gui.chat.telegram_gateway.telegram_worker import _start_telegram_poller
from gui.components.rag_tab import build_rag_tab
from gui.components.role_llm_inspector_tab import build_role_llm_inspector_tab
from gui.components.settings import (
    build_settings_tab,
    get_window_height,
    get_window_width,
    get_left_panel_width,
    get_right_panel_width,
    get_left_panel_is_visible,
    get_right_panel_is_visible,
    get_workflow_project_name,
    get_workflow_save_dir,
    save_settings,
    UNITS_DIR,
)
from rag.ragconf_loader import (
    rag_update_workflow_server_endpoint_raw,
    rag_update_response_endpoint_raw,
    rag_update_response_timeout_s_raw
)
from gui.components.training_tab import build_training_tab
from gui.components.workflow_tab import build_workflow_tab
from gui.components.workflow_tab.dialogs.dialog_save_workflow import (
    save_workflow_version,
)
from gui.components.workflow_tab.workflows.core_workflows import (
    run_load_workflow_inline,
    run_runtime_label_inline,
)
from gui.utils.keyboard_commands import create_keyboard_handler
from gui.utils.notifications import show_toast
from gui.utils.ollama_runner import maybe_start_ollama
from gui.chat.ui.progress_bar import TurnProgressBar
from gui.chat.hooks import on_turn_status_hook
from gui.components.progress_overlay import build_progress_overlay

from gui.chat.graph_bridge import register_live_graph_accessors
from gui.chat.hooks import on_apply_hook
from gui.chat.utils.ui_utils import _toast
from gui.components.workflow_tab.workflows.core_workflows import (
    validate_graph_to_apply_for_canvas_inline,
)

# Import flet-code-editor early so Flet registers the CodeEditor control (avoids "Unknown control: CodeEditor")
try:
    import flet_code_editor  # noqa: F401
except ImportError:
    pass

# Ensure FilePicker control is registered (avoids "Unknown control: FilePicker" on some Flet clients)
from flet.controls.services.file_picker import FilePicker  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# A timeframe in seconds to wait for the RAG update to finish. I might take long, especially when handling lots of new files to injest.
RAG_UPDATE_TIMEOUT_S = rag_update_response_timeout_s_raw()
RAG_UPDATE_WORKFLOW_SERVER_ENDPOINT = rag_update_workflow_server_endpoint_raw()
RAG_UPDATE_RESPONSE_ENDPOINT = rag_update_response_endpoint_raw()

logger = logging.getLogger(__name__)


# Panel layout
LEFT_PANEL_MIN = 80
LEFT_PANEL_MAX = 280
LEFT_PANEL_DEFAULT = 100
RIGHT_PANEL_MIN = 300
RIGHT_PANEL_MAX = 520
RIGHT_PANEL_DEFAULT = 320
RESIZE_GRIP_WIDTH = 4
COLLAPSED_PANEL_WIDTH = 12
RESIZE_UPDATE_INTERVAL_S = (
    1 / 10
)  # Throttle panel resize to ~10fps to avoid lag when graph is visible
LEFT_PANEL_WIDTH_KEY_FALLBACK = LEFT_PANEL_DEFAULT
RIGHT_PANEL_WIDTH_KEY_FALLBACK = RIGHT_PANEL_DEFAULT


# --- Wrapper for async show_toast ---
def show_toast_sync(page: Page, message: str) -> None:
    """
    Fire-and-forget wrapper around async show_toast.
    Can be passed to functions expecting a sync callable.
    """
    # schedule the async function to run in the background
    asyncio.create_task(show_toast(page, message))


async def main(page: ft.Page) -> None:
    # --- STARTUP SPINNER ---
    spinner = ft.ProgressRing(width=60, height=60, stroke_width=6)

    spinner_overlay = ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        bgcolor=ft.Colors.BLACK,
        opacity=0.25,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                spinner,
                ft.Text("AI TaskVector…", size=14, color=ft.Colors.GREY_300),
            ],
        ),
        visible=True,
    )

    page.overlay.append(spinner_overlay)
    page.update()
    # --- END STARTUP SPINNER ---

    # Sync config/prompts/*.json from agents/prompts.py before chat/workflow load templates.
    try:
        from scripts.write_prompt_templates import build_prompt_templates

        _ok, _msg = build_prompt_templates(None, None)
        if not _ok:
            print(f"Prompt templates sync failed: {_msg}", file=sys.stderr)
    except Exception as _e:
        print(f"Prompt templates sync failed: {_e}", file=sys.stderr)

    # Apply saved or default window size (Flet 0.27+: size lives on page.window, not page.window_*).
    page.window.width = get_window_width()
    page.window.height = get_window_height()
    page.update()

    # Persist window size on resize (throttled)
    _last_window_size_save: list[float] = [0.0]
    WINDOW_SIZE_SAVE_THROTTLE_S = 1.0

    def _save_window_size_on_resize(e: ft.PageResizeEvent) -> None:
        now = time.perf_counter()
        if now - _last_window_size_save[0] < WINDOW_SIZE_SAVE_THROTTLE_S:
            return
        _last_window_size_save[0] = now
        w = e.width
        h = e.height
        if w is not None and h is not None and w > 0 and h > 0:
            try:
                save_settings(window_width=int(w), window_height=int(h))
            except Exception:
                pass

    page.on_resize = _save_window_size_on_resize

    async def _node_red_tab_label(graph: ProcessGraph | None) -> str | None:
        """Try to read Node-RED tab label from origin metadata (only when runtime is node_red)."""
        if graph is None:
            return None
        label, _ = await run_runtime_label_inline(graph)
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

    async def _set_page_title(graph: ProcessGraph | None) -> None:
        project_name = get_workflow_project_name()
        tab_label = await _node_red_tab_label(graph)
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

    await _set_page_title(None)
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    # Load the most recently modified workflow from the save folder; else new-flow template; else empty
    graph_ref: list[ProcessGraph | None] = [None]
    _new_flow_template_path = (
        Path(__file__).resolve().parent
        / "components"
        / "workflow"
        / "import"
        / "new_flow_template.json"
    )
    save_dir = get_workflow_save_dir()
    if save_dir.exists():
        json_files = list(save_dir.glob("*.json"))
        if json_files:
            latest = max(json_files, key=lambda p: p.stat().st_mtime)
            try:
                graph_dict, err = await run_load_workflow_inline(str(latest))
                if not err and graph_dict is not None:
                    graph_ref[0] = ProcessGraph.model_validate(graph_dict)
                elif err:
                    print(f"Could not load workflow {latest}: {err}")
            except Exception as e:
                print(f"Could not load workflow {latest}: {e}")
    if graph_ref[0] is None and _new_flow_template_path.is_file():
        try:
            graph_dict, err = await run_load_workflow_inline(
                str(_new_flow_template_path), format="dict"
            )
            if not err and graph_dict is not None:
                graph_ref[0] = ProcessGraph.model_validate(graph_dict)
        except Exception:
            pass
    await _set_page_title(graph_ref[0])

    chat_panel_api: dict[str, Any] = {}

    # Workflow tab (process graph + code view + dialogs)
    def _on_graph_changed(graph: ProcessGraph | None) -> None:
        asyncio.create_task(_set_page_title(graph))

    (
        process_tab_column,
        _set_graph_base,
        apply_from_agent,
        get_recent_changes,
        workflow_undo,
        workflow_redo,
        show_console_with_run_output,
    ) = build_workflow_tab(
        page,
        graph_ref,
        show_toast_sync,
        on_graph_changed=_on_graph_changed,
        chat_graph_drag_group=CHAT_GRAPH_DRAG_GROUP,
        chat_panel_api=chat_panel_api,
    )

    def set_graph(graph: ProcessGraph | None) -> None:
        _set_graph_base(graph)
        asyncio.create_task(_set_page_title(graph))

   # --- Integrate the live graph_bridge to apply graph from external messengers ---

    _external_apply_state: dict[str, Any] = {
        "last_graph_to_apply": None,
        "graph_apply_error": None,
        "graph_applied": False,
        "is_initial_apply_done": False,
    }

    def _live_graph_dict() -> dict[str, Any] | None:
        g = graph_ref[0]
        if g is None:
            return None
        if hasattr(g, "model_dump"):
            return g.model_dump(by_alias=True)
        return g if isinstance(g, dict) else None

    async def _apply_graph_from_external_turn(inner_msg: dict[str, Any]) -> None:
        await on_apply_hook(
            token=0,
            inner_msg=inner_msg,
            page=page,
            is_current_run=lambda _t: True,
            toast=_toast,
            validate_graph_inline=validate_graph_to_apply_for_canvas_inline,
            safe_page_update=lambda p: p.update(),
            scroll_chat_to_bottom=lambda: asyncio.sleep(0),
            apply_fn_from_agent=apply_from_agent,
            set_graph=set_graph,
            state=_external_apply_state,
        )

    register_live_graph_accessors(
        get_graph_dict=_live_graph_dict,
        on_apply_graph=_apply_graph_from_external_turn,
    )

    # Placeholder tabs
    training_content = build_training_tab(
        page,
        graph_ref=graph_ref,
        show_toast=show_toast_sync,
        chat_panel_api=chat_panel_api,
    )
    rag_content = build_rag_tab(
        page, show_rag_preview=_dev_mode(), chat_panel_api=chat_panel_api
    )
    settings_content = build_settings_tab(
        page,
        on_saved=lambda: chat_panel_api.get("refresh_model_label", lambda: None)(),
    )
    dev = _dev_mode()
    if dev:
        role_llm_inspector = build_role_llm_inspector_tab(page, chat_panel_api)
        contents = [
            process_tab_column,
            training_content,
            rag_content,
            role_llm_inspector,
            settings_content,
        ]
        settings_content_index = 4
        max_rail_index = 3
    else:
        contents = [process_tab_column, training_content, rag_content, settings_content]
        settings_content_index = 3
        max_rail_index = 2
    content_col = ft.Column(controls=[contents[0]], expand=True)
    active_tab_idx: list[int] = [0]

    # Lightweight placeholder shown while resizing to avoid expensive repaints
    resize_placeholder = ft.Container(
        expand=True,
        bgcolor=ft.Colors.GREY_900,
        content=ft.Row(
            controls=[ft.Text("Resizing…", size=12, color=ft.Colors.GREY_500)],
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
            content_col.controls = [contents[0]]
            active_tab_idx[0] = 0
            _sync_left_nav_chrome()
            page.update()
        show_console_with_run_output(run_output)

    rail_destinations = [
        ft.NavigationRailDestination(icon=ft.Icons.ACCOUNT_TREE, label="Flow"),
        ft.NavigationRailDestination(icon=ft.Icons.TUNE, label="Gym"),
        ft.NavigationRailDestination(icon=ft.Icons.FOLDER_OPEN, label="Data"),
    ]
    if dev:
        rail_destinations.append(
            ft.NavigationRailDestination(
                icon=ft.Icons.VISIBILITY_OUTLINED,
                label="LLM",
            )
        )

    turn_progress_bar = TurnProgressBar() # <- TaskVector native chat
    on_turn_status = on_turn_status_hook(page, turn_progress_bar)


    # Right column: agents chat panel
    chat_content = build_agents_chat_panel(
        page,
        graph_ref=graph_ref,
        set_graph=set_graph,
        apply_from_agent=apply_from_agent,
        get_recent_changes=get_recent_changes,
        on_undo=_undo_if_workflow,
        on_redo=_redo_if_workflow,
        show_run_current_graph=_dev_mode(),
        on_show_run_console=on_show_run_console_from_chat,
        chat_panel_api=chat_panel_api,
        on_turn_status=on_turn_status,
    )

    def on_rail_change(e: Event[ft.NavigationRail]) -> None:
        rail = e.control  # type is ft.NavigationRail
        idx = rail.selected_index
        if idx is None or idx < 0:
            idx = 0
        if idx <= max_rail_index:
            content_col.controls = [contents[idx]]
            active_tab_idx[0] = idx
        _sync_left_nav_chrome()
        page.update()

    def on_settings_click(e: Event[ft.IconButton]) -> None:
        content_col.controls = [contents[settings_content_index]]
        active_tab_idx[0] = settings_content_index
        _sync_left_nav_chrome()
        page.update()

    LEFT_NAV_ICON_ACTIVE = ft.Colors.GREY_200
    LEFT_NAV_ICON_INACTIVE = ft.Colors.GREY_600

    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=60,
        destinations=rail_destinations,
        on_change=on_rail_change,
    )

    settings_btn = ft.IconButton(
        icon=ft.Icons.SETTINGS,
        tooltip="Settings",
        on_click=on_settings_click,
        icon_color=LEFT_NAV_ICON_INACTIVE,
    )

    def _sync_left_nav_chrome() -> None:
        """Keep rail selection and settings icon in sync with ``active_tab_idx``."""
        if active_tab_idx[0] == settings_content_index:
            nav_rail.selected_index = None
            settings_btn.icon_color = LEFT_NAV_ICON_ACTIVE
        else:
            idx = active_tab_idx[0]
            if 0 <= idx <= max_rail_index:
                nav_rail.selected_index = idx
            settings_btn.icon_color = LEFT_NAV_ICON_INACTIVE
        try:
            nav_rail.update()
            settings_btn.update()
        except Exception:
            pass

    # Panel state
    # Read persisted values (use your existing load/settings-get logic)
    saved_left_visible = get_left_panel_is_visible()
    saved_right_visible = get_right_panel_is_visible()
    left_visible: list[bool] = [saved_left_visible]

    left_expanded_width: list[float] = [
        float(get_left_panel_width() or LEFT_PANEL_DEFAULT)
    ]
    left_width: list[float] = [left_expanded_width[0]]  # current width (changes during resize / collapse)

    right_visible: list[bool] = [saved_right_visible]

    right_expanded_width: list[float] = [
        float(get_right_panel_width() or RIGHT_PANEL_DEFAULT)
    ]
    right_width: list[float] = [right_expanded_width[0]]  # current width (changes during resize)



    # Throttle UI updates during drag (resize events)
    last_resize_update: list[float] = [0.0]

    # Persist panel widths (throttled like window size)
    _left_right_size_save: list[float] = [0.0]
    LEFT_RIGHT_SIZE_SAVE_THROTTLE_S = 1.0

    def _save_left_right_widths() -> None:
        now = time.perf_counter()
        if now - _left_right_size_save[0] < LEFT_RIGHT_SIZE_SAVE_THROTTLE_S:
            return
        _left_right_size_save[0] = now
        try:
            save_settings(
                left_panel_visible=bool(left_visible[0]),
                right_panel_visible=bool(right_visible[0]),
                left_panel_width=int(left_expanded_width[0]),
                right_panel_width=int(right_expanded_width[0]),
            )
        except Exception:
            pass


    def _resize_begin(e: DragStartEvent) -> None:
        """Enter lightweight resize mode to reduce lag (esp. Workflow canvas)."""
        if resizing[0]:
            return
        resizing[0] = True
        # Only swap out the heavy Workflow tab during drag; other tabs are cheap.
        if active_tab_idx[0] <= max_rail_index:
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

    def _resize_flush(e: DragEndEvent) -> None:
        left_panel_container.width = left_width[0]
        right_panel_container.width = right_width[0]
        left_panel_container.update()
        right_panel_container.update()
        _resize_end()
        _save_left_right_widths()


    # Resize grip (draggable vertical strip)
    def make_left_grip():
        return ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=20,
            on_horizontal_drag_start=_resize_begin,
            on_horizontal_drag_update=_resize_left,  # pass directly (no lambda)
            on_horizontal_drag_end=_resize_flush,
            content=ft.Container(
                width=RESIZE_GRIP_WIDTH,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )

    # Border for right resize edge (static; no hover highlight)
    _right_edge_border = ft.Border.only(left=ft.BorderSide(0.4, ft.Colors.GREY_700))

    def make_right_grip():
        return ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
            drag_interval=20,
            on_horizontal_drag_start=_resize_begin,
            on_horizontal_drag_update=_resize_right,  # pass directly
            on_horizontal_drag_end=_resize_flush,
            content=ft.Container(
                width=RESIZE_GRIP_WIDTH,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )

    def _resize_left(e: DragUpdateEvent) -> None:
        # Optional safety: don’t resize while collapsed
        if not left_visible[0]:
            return

        delta_x = e.local_delta.x if e.local_delta else 0.0
        if delta_x is None:
            delta_x = 0.0
        delta = delta_x

        w = left_expanded_width[0] + delta  # drag right = expand
        w = max(LEFT_PANEL_MIN, min(LEFT_PANEL_MAX, w))

        left_expanded_width[0] = w
        left_width[0] = w
        left_panel_container.width = w

        now = time.perf_counter()
        if now - last_resize_update[0] >= RESIZE_UPDATE_INTERVAL_S:
            last_resize_update[0] = now
            left_panel_container.update()


    def _resize_right(e: DragUpdateEvent) -> None:
        # Optional safety: don’t resize while collapsed
        if not right_visible[0]:
            return

        delta_x = e.local_delta.x if e.local_delta else 0.0
        if delta_x is None:
            delta_x = 0.0
        delta = delta_x

        w = right_expanded_width[0] - delta  # drag left = shrink
        w = max(RIGHT_PANEL_MIN, min(RIGHT_PANEL_MAX, w))

        right_expanded_width[0] = w
        right_width[0] = w
        right_panel_container.width = w

        now = time.perf_counter()
        if now - last_resize_update[0] >= RESIZE_UPDATE_INTERVAL_S:
            last_resize_update[0] = now
            right_panel_container.update()


    def toggle_left(_e: Event[ft.IconButton]) -> None:
        left_visible[0] = not left_visible[0]

        if left_visible[0]:
            # Expanding: restore remembered expanded width
            left_panel_container.content = left_expanded_row
            left_width[0] = left_expanded_width[0]
            left_panel_container.width = left_width[0]
        else:
            # Collapsing: set container to collapsed but keep expanded width remembered
            left_panel_container.content = left_collapsed_content
            left_panel_container.width = COLLAPSED_PANEL_WIDTH
            left_width[0] = COLLAPSED_PANEL_WIDTH

        left_panel_container.update()
        _save_left_right_widths()
        page.update()


    def toggle_right(_e: Event[ft.IconButton]) -> None:
        right_visible[0] = not right_visible[0]

        if right_visible[0]:
            # Expanding: restore remembered expanded width
            right_panel_container.content = right_expanded_row
            right_width[0] = right_expanded_width[0]
            right_panel_container.width = right_width[0]
        else:
            # Collapsing: shrink container but keep expanded width remembered
            right_panel_container.content = right_collapsed_content
            right_panel_container.width = COLLAPSED_PANEL_WIDTH
            right_width[0] = COLLAPSED_PANEL_WIDTH

        right_panel_container.update()
        _save_left_right_widths()
        page.update()


    # Shared chevron style for left/right collapse buttons
    _chevron_style = ft.ButtonStyle(
        padding=0,
        shape=ft.RoundedRectangleBorder(radius=4),
    )

    def _collapse_chevron(
        icon: ft.IconDataOrControl,
        on_click: ControlEventHandler[ft.IconButton],
    ) -> ft.IconButton:
        return ft.IconButton(
            icon=icon,
            on_click=on_click,
            icon_size=12,
            style=_chevron_style,
            width=12,
            height=12,
        )

    left_rail_column = ft.Column(
        controls=[
            ft.Container(content=nav_rail, expand=True),
            ft.Container(content=settings_btn, padding=4),
        ],
        expand=True,
        spacing=0,
    )

    left_collapsed_content = ft.Row(
        controls=[
            _collapse_chevron(ft.Icons.CHEVRON_RIGHT, toggle_left),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    left_expanded_row = ft.Row(
        controls=[
            _collapse_chevron(ft.Icons.CHEVRON_LEFT, toggle_left),
            left_rail_column,
            make_left_grip(),
        ],
        spacing=0,
    )

    left_panel_container = ft.Container(
        content=left_expanded_row,
        width=left_width[0],
    )

    right_collapsed_content = ft.Row(
        controls=[
            _collapse_chevron(ft.Icons.CHEVRON_LEFT, toggle_right),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    right_chat_wrapper = ft.Container(
        content=chat_content,
        padding=ft.Padding.only(left=2, top=4, bottom=4, right=2),
        expand=True,
    )

    right_edge_container = ft.Container(
        border=_right_edge_border,
        content=make_right_grip(),
    )

    right_expanded_row = ft.Row(
        controls=[
            right_edge_container,
            right_chat_wrapper,
            _collapse_chevron(ft.Icons.CHEVRON_RIGHT, toggle_right),
        ],
        spacing=0,
    )

    right_panel_container = ft.Container(
        content=right_expanded_row,
        width=right_width[0],
    )

    # Apply persisted collapsed/expanded state on startup
    def _apply_initial_panel_state():
        # LEFT
        if left_visible[0]:
            left_panel_container.content = left_expanded_row
            left_width[0] = left_expanded_width[0]
            left_panel_container.width = left_width[0]
        else:
            left_panel_container.content = left_collapsed_content
            left_width[0] = float(COLLAPSED_PANEL_WIDTH)
            left_panel_container.width = COLLAPSED_PANEL_WIDTH

        # RIGHT
        if right_visible[0]:
            right_panel_container.content = right_expanded_row
            # Use remembered expanded width, not whatever the collapsed width was
            right_width[0] = right_expanded_width[0]
            right_panel_container.width = right_width[0]
        else:
            right_panel_container.content = right_collapsed_content
            right_width[0] = float(COLLAPSED_PANEL_WIDTH)
            right_panel_container.width = COLLAPSED_PANEL_WIDTH


    # Apply persisted collapsed/expanded state on startup
    _apply_initial_panel_state()

    # Layout
    layout = ft.Column(
        controls=[
            turn_progress_bar.control(),
            ft.Row(
                controls=[
                    left_panel_container,
                    ft.VerticalDivider(width=1),
                    content_col,
                    right_panel_container,
                ],
                expand=True,
                spacing=0,
            ),
        ],
        expand=True,
        spacing=0,
    )

    progress_overlay, show_overlay, hide_overlay = build_progress_overlay()

    page.add(
        ft.Stack(
            expand=True,
            controls=[
                layout,            # bottom layer (your UI)
                progress_overlay, # top layer (spinner overlay)
            ],
        )
    )

    page.update()

    # --- hide startup spinner BEFORE starting background startup tasks ---
    spinner_overlay.visible = False
    spinner.visible = False
    if spinner_overlay in page.overlay:
        page.overlay.remove(spinner_overlay)
    page.update()

    _tasks: List[Any] = []

    page.on_keyboard_event = on_keyboard

    async def _rag_startup() -> None:
        from gui.components.settings import (
            get_mydata_dir,
            get_rag_embedding_model,
            get_rag_index_dir,
            get_rag_update_workflow_path,
        )
        from gui.utils.rag_update_handler import RagUpdateViaZmq

        show_overlay("RAG: indexing...")
        page.update()

        async def hide_then_toast(msg: str):
            hide_overlay()
            page.update()
            await show_toast(page, msg)

        try:
            pub_endpoint = RAG_UPDATE_WORKFLOW_SERVER_ENDPOINT
            sub_endpoint = RAG_UPDATE_RESPONSE_ENDPOINT

            workflow_path = get_rag_update_workflow_path()
            if not workflow_path.exists():
                await hide_then_toast("RAG: rag_update workflow not found")
                return

            overrides = {
                "rag_update": {
                    "rag_index_data_dir": str(get_rag_index_dir()),
                    "units_dir": str(UNITS_DIR),
                    "mydata_dir": str(get_mydata_dir()),
                    "embedding_model": get_rag_embedding_model(),
                },
            }

            async def on_response(payload: dict):
                msg = (
                    str(
                        ((payload or {}).get("response", {}) or {}).get("message")
                        or ((payload or {}).get("response", {}) or {}).get("details")
                        or "RAG is up to date"
                    )[:150]
                )
                await hide_then_toast(msg)

            async def on_error(err: str, payload: dict):
                msg = f"RAG update error: {str(err)[:150]}"
                await hide_then_toast(msg)

            updater = RagUpdateViaZmq(
                pub_endpoint=pub_endpoint,
                sub_endpoint=sub_endpoint,
                response_timeout_s=RAG_UPDATE_TIMEOUT_S,
                on_response=on_response,
                on_error=on_error,
            )

            await updater.run(
                workflow_path=str(workflow_path),
                initial_inputs=None,
                unit_param_overrides=overrides,
            )

            # safety: if no callback fired
            hide_overlay()
            page.update()

        except Exception as e:
            hide_overlay()
            page.update()
            await show_toast(page, f"RAG update failed: {str(e)[:150]}")

    _zmq_handler = None

    async def _zmq_startup() -> None:
        nonlocal _zmq_handler
        from gui.utils.flet_zmq_handler import FletZmqHandler

        # Mount once
        if _zmq_handler is None:
            logger.info("_zmq_startup: creating FletZmqHandler")
            _zmq_handler = FletZmqHandler()
            try:
                # Prefer page.overlay if available (it's ideal for overlays)
                if hasattr(page, "overlay") and isinstance(page.overlay, list):
                    page.overlay.append(_zmq_handler)
                else:
                    page.controls.append(_zmq_handler)
            except Exception:
                # If mount fails, don't crash the whole task
                logger.exception("_zmq_startup: failed to mount control; continuing")

            # Best-effort update; ignore if session is already tearing down
            try:
                page.update()
            except RuntimeError:
                logger.info("_zmq_startup: page.update after mount failed (session destroyed); ignoring")

        # Keep the task running so cancel() can trigger cleanup
        try:
            while True:
                await asyncio.sleep(3600)

        except asyncio.CancelledError:
            # IMPORTANT: during shutdown, Flet session may already be destroyed.
            logger.info("_zmq_startup: CancelledError (cleanup/unmount)")

            # Unmount (best-effort, never fail shutdown)
            try:
                if _zmq_handler is not None:
                    if (
                        hasattr(page, "overlay")
                        and isinstance(page.overlay, list)
                        and _zmq_handler in page.overlay
                    ):
                        page.overlay.remove(_zmq_handler)
                    elif _zmq_handler in getattr(page, "controls", []):
                        page.controls.remove(_zmq_handler)
            except Exception:
                logger.exception("_zmq_startup: unmount failed; ignoring")
            return

    async def _ollama_startup() -> None:
        ok, msg = await asyncio.to_thread(maybe_start_ollama)
        if msg and not ok:
            await show_toast(page, f"Ollama: {msg}")
        elif msg and ok and "already" not in msg.lower():
            await show_toast(page, "Ollama started")

    async def _telegram_startup() -> None:
        ok, msg = await _start_telegram_poller()
        if msg and not ok:
            await show_toast(page, f"Telegram poller: {msg}")
        elif msg and ok and "already" not in msg.lower():
            await show_toast(page, "Telegram poller started")

    # register handlers once and store returned futures (could be concurrent.futures.Future or asyncio.Future)
    _tasks = [
        page.run_task(_zmq_startup),
        page.run_task(_rag_startup),
        page.run_task(_ollama_startup),
        page.run_task(_telegram_startup),
    ]

    # shutdown: cancel/await stored futures where supported
    async def clean_shutdown() -> None:
        for f in list(_tasks):
            try:
                if hasattr(f, "cancel"):
                    f.cancel()
            except Exception:
                pass

        asyncio_futures = [f for f in _tasks if isinstance(f, asyncio.Future)]
        if asyncio_futures:
            await asyncio.gather(*asyncio_futures, return_exceptions=True)


def _dev_mode() -> bool:
    """True when run with -dev or --dev (e.g. python -m gui.main -dev)."""
    return "-dev" in sys.argv or "--dev" in sys.argv


def _web_server_config() -> tuple[bool, int, str]:
    """(use_web, port, host). When FLET_WEB=1 or FLET_SERVER_PORT is set, run as web server (e.g. in Docker)."""
    import os

    port_str = (os.environ.get("FLET_SERVER_PORT") or "").strip()
    web = (os.environ.get("FLET_WEB") or "").strip() in ("1", "true", "yes") or bool(
        port_str
    )
    port = int(port_str) if port_str.isdigit() else 8550
    host = (os.environ.get("FLET_SERVER_HOST") or "").strip() or "0.0.0.0"
    return web, port, host


if __name__ == "__main__":
    use_web, port, host = _web_server_config()
    if use_web:
        ft.run(main, view=ft.AppView.WEB_BROWSER, port=port, host=host)
    else:
        ft.run(main)
