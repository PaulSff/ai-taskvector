"""Shared RAG UI: copy local path or fetch URL, then save via Flet FilePicker (desktop vs web/mobile)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import flet as ft

from gui.utils.file_picker import register_file_picker
from gui.utils.notifications import show_toast


def prepare_download_name_and_bytes(path_or_url: str) -> tuple[str, bytes]:
    """
    Load bytes for a local file path or http(s) URL. Returns (suggested_filename, data).
    Raises OSError / urllib.error on failure.
    """
    p = (path_or_url or "").strip()
    if p.startswith(("http://", "https://")):
        import urllib.request

        req = urllib.request.Request(p, headers={"User-Agent": "Flet-RAG/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        name = Path(urlparse(p).path).name or "downloaded"
        if not name or name == ".":
            name = "downloaded"
        return name, data
    lp = Path(p).expanduser()
    if not lp.is_file():
        raise FileNotFoundError(p)
    return lp.name, lp.read_bytes()


def needs_src_bytes_for_save(page: ft.Page) -> bool:
    """Web and mobile require ``src_bytes`` in Flet ``save_file``."""
    if getattr(page, "web", False):
        return True
    plat = getattr(page, "platform", None)
    if plat is not None and getattr(plat, "is_mobile", lambda: False)():
        return True
    return False


async def download_path_or_url_to_disk(page: ft.Page, path_or_url: str) -> None:
    """Read path/URL bytes, open save dialog, write file; toasts on outcome."""
    p = (path_or_url or "").strip()
    if not p:
        return
    fp = register_file_picker(page)
    if not fp:
        await show_toast(page, "File picker not available")
        return
    try:
        name, data = await asyncio.to_thread(prepare_download_name_and_bytes, p)
    except Exception as ex:
        await show_toast(page, f"Could not read: {ex}"[:120])
        return
    if not data:
        await show_toast(page, "Empty file")
        return
    try:
        if needs_src_bytes_for_save(page):
            await fp.save_file(
                dialog_title="Save file",
                file_name=name,
                src_bytes=data,
            )
            await show_toast(page, "Download complete")
        else:
            dest = await fp.save_file(dialog_title="Save file", file_name=name)
            if dest:
                await asyncio.to_thread(Path(dest).write_bytes, data)
                await show_toast(page, "File saved")
            else:
                await show_toast(page, "Save cancelled")
    except Exception as ex:
        await show_toast(page, f"Save failed: {ex}"[:120])
