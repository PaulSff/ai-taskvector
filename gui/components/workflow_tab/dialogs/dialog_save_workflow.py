from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import flet as ft

from agents.chat.utils.save_workflow import (
    _now_timestamp,
    save_workflow_version,
)
from core.schemas.process_graph import ProcessGraph
from gui.components.settings import (
    get_workflow_project_name,
    get_workflow_save_path_template,
    save_settings,
)
from gui.utils.notifications import show_toast


def open_save_workflow_dialog(
    page: ft.Page,
    graph_or_ref: ProcessGraph | dict | list[ProcessGraph | dict | None] | None,
    *,
    on_saved: Callable[[Path], None] | None = None,
) -> None:
    def _get_graph() -> ProcessGraph | dict | None:
        if isinstance(graph_or_ref, list) and len(graph_or_ref) > 0:
            return graph_or_ref[0]
        return graph_or_ref  # type: ignore[return-value]

    def _toast(msg: str) -> None:
        async def _run() -> None:
            await show_toast(page, msg)

        page.run_task(_run)

    def _close() -> None:
        dlg.open = False
        page.update()

    initial_project = get_workflow_project_name()
    template_from_settings = get_workflow_save_path_template()

    project_tf = ft.TextField(
        label="Project name",
        value=initial_project,
        width=340,
        autofocus=True,
    )

    folder_tf = ft.TextField(
        label="Folder",
        value="",
        read_only=True,
        width=340,
    )

    # Default filename: timestamped, with .json
    def _default_filename() -> str:
        return f"workflow_{_now_timestamp()}.json"

    filename_tf = ft.TextField(
        label="Filename",
        value=_default_filename(),
        width=340,
    )

    preview_txt = ft.Text(value="", selectable=True)

    from gui.utils.file_picker import register_file_picker

    file_picker = register_file_picker(page)

    def _ensure_json_suffix(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return s
        p = Path(s)
        if p.suffix:
            return s
        return s + ".json"

    def _update_preview() -> None:
        folder = (folder_tf.value or "").strip()
        name = (filename_tf.value or "").strip()
        name = _ensure_json_suffix(name) if name else name
        preview_path = str(Path(folder) / name)
        preview_txt.value = (
            f"Preview: {preview_path}"
            if folder and name
            else "Preview: (pick folder + enter filename)"
        )

        try:
            preview_txt.update()
        except RuntimeError:
            pass

    project_tf.on_change = lambda _e: _update_preview()
    filename_tf.on_change = lambda _e: _update_preview()

    _pick_busy = False

    def _pick_folder() -> None:
        nonlocal _pick_busy
        if _pick_busy:
            return
        nonlocal file_picker
        if file_picker is None:
            _toast("File picker not available.")
            return
        picker = file_picker  # for type checkers: now not None


        _pick_busy = True

        async def _task() -> None:
            nonlocal _pick_busy
            try:
                folder = await picker.get_directory_path()
                if not folder:
                    return
                folder_tf.value = folder
                folder_tf.update()
                _update_preview()
            except RuntimeError as ex:
                _toast(f"Folder picker error: {ex}")
            finally:
                _pick_busy = False

        page.run_task(_task)


    def _save_click(e: ft.Event[ft.Button]) -> None:
        proj = (project_tf.value or "").strip() or "my_project"
        folder = (folder_tf.value or "").strip()
        filename = _ensure_json_suffix((filename_tf.value or "").strip())

        if not folder:
            _toast("Pick a folder first.")
            return
        if not filename:
            _toast("Enter a filename.")
            return

        # Keep your existing Settings persistence behavior
        try:
            save_settings(
                workflow_project_name=proj,
                workflow_save_path_template=template_from_settings,
            )
        except OSError:
            pass

        # Build a template that matches your resolver contract:
        # - It must contain $PROJECT_NAME$ and $YY-MM-DD-HHMMSS$
        # - We embed chosen absolute folder as a fixed string prefix.
        #
        # Also: we want the user to control the filename "around" the timestamp.
        # We'll replace/augment the filename so it becomes timestamped by your saver:
        #   - if user filename already contains $YY-MM-DD-HHMMSS$ token -> keep
        #   - else insert timestamp token before extension.
        base = Path(filename).stem
        suffix = Path(filename).suffix or ".json"

        # If user already included your timestamp token, keep it; otherwise insert it.
        ts_token = "$YY-MM-DD-HHMMSS$"
        if ts_token in filename:
            user_name_template = Path(filename).name
        else:
            user_name_template = f"{base}_{ts_token}{suffix}"

        # Put $PROJECT_NAME$ into the filename template too, so resolver substitution works.
        proj_token = "$PROJECT_NAME$"
        if proj_token not in user_name_template:
            user_name_template = f"{user_name_template}"

        abs_folder = str(Path(folder).resolve())
        user_template = str(Path(abs_folder) / user_name_template)

        result = save_workflow_version(
            _get_graph(),
            project_name=proj,
            template=user_template,
        )

        if result.reason == "saved" and result.path is not None:
            _toast("Saved!")
            if on_saved:
                on_saved(result.path)
            _close()
            return
        if result.reason == "no_changes":
            _toast("No changes to save")
            return
        if result.reason == "no_graph":
            _toast("No workflow loaded")
            return
        _toast("Save failed")

    # initial preview
    _update_preview()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Save workflow as"),
        content=ft.Container(
            content=ft.Column(
                controls=cast(
                    list[ft.Control],
                    [
                        ft.Text(
                            "Choose a destination folder and filename. "
                            "A new timestamped file is written only if the workflow changed (MD5 vs latest).",
                            size=12,
                            color=ft.Colors.GREY_500,
                        ),
                        ft.Container(height=10),
                        project_tf,
                        ft.Container(height=6),
                        ft.Row(
                            controls=cast(
                                list[ft.Control],
                                [
                                    ft.OutlinedButton("Pick folder…", on_click=_pick_folder),

                                ],
                            ),
                            spacing=8,
                        ),
                        ft.Container(height=6),
                        folder_tf,
                        ft.Container(height=6),
                        filename_tf,
                        ft.Container(height=8),
                        preview_txt,
                        ft.Container(height=8),
                        ft.Row(
                            controls=cast(
                                list[ft.Control],
                                [
                                    ft.Button("Save", on_click=_save_click),
                                    ft.TextButton("Cancel", on_click=lambda _e: _close()),
                                ],
                            ),
                            spacing=8,
                        ),
                    ],
                ),
                tight=True,
                spacing=6,
            ),
            width=700,
        ),
    )

    page.overlay.append(dlg)
    dlg.open = True
    page.update()
    _update_preview()
