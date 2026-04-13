"""
Flet FilePicker for v0.80+ (breaking API change: do NOT add to page.overlay).

Per https://docs.flet.dev/services/filepicker/#examples:
  file_picker = ft.FilePicker()
  # In async handler: files = await file_picker.pick_files(allow_multiple=True)
  # Do NOT use page.overlay.append(file_picker) — that was the old API and causes "Unknown control: FilePicker".
"""
from __future__ import annotations

import flet as ft


def register_file_picker(page: ft.Page) -> ft.FilePicker | None:
    """
    Create a FilePicker for v0.80+ and return it. Do not add to page.overlay.
    Caller uses async: files = await picker.pick_files(allow_multiple=True).
    """
    try:
        return ft.FilePicker()
    except Exception:
        return None
