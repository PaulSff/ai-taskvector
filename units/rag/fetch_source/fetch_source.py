"""
FetchSource unit: unified source resolver for RAG ingestion pipelines.

Accepts any source string and produces a **resolved local file path** that every
downstream unit (starting with FileTypeDetector) can handle uniformly.

| Source type      | Behaviour                                                         |
|------------------|-------------------------------------------------------------------|
| Local file path  | Verifies existence; outputs the resolved absolute path.           |
| http / https     | Downloads to ``save_dir``; outputs the saved local path.          |
| ftp / ftps       | Downloads via ``urllib`` to ``save_dir``; outputs the local path. |

Downloaded files are stored **persistently** in ``save_dir`` (not a temp directory).
A file already present at the target path is not re-downloaded unless ``overwrite``
is ``True``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from units.registry import UnitSpec, register_unit

FETCH_SOURCE_INPUT_PORTS = [("source", "Any")]
FETCH_SOURCE_OUTPUT_PORTS = [
    ("file_path", "str"),
    ("source", "str"),
    ("fetched", "Any"),
    ("error", "str"),
]

_HTTP_SCHEMES = frozenset({"http", "https"})
_FTP_SCHEMES = frozenset({"ftp", "ftps"})
_REMOTE_SCHEMES = _HTTP_SCHEMES | _FTP_SCHEMES


# -----------------------------
# Helpers
# -----------------------------


def _filename_from_url(url: str) -> str:
    """
    Derive a stable, collision-resistant local filename from a URL.

    Uses a SHA-256 prefix so two different URLs that share the same basename
    never collide, while the original extension is preserved for type detection.
    """
    parsed = urlparse(url)
    suffix = Path(parsed.path.rstrip("/")).suffix.lower()
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{h}{suffix}" if suffix else h


def _fetch_http(url: str, dest: Path) -> None:
    """Stream-download an HTTP/HTTPS URL to *dest*."""
    import requests

    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=65_536):
            if chunk:
                fh.write(chunk)


def _fetch_ftp(url: str, dest: Path) -> None:
    """Download an FTP/FTPS URL to *dest* via ``urllib``."""
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)  # noqa: S310


# -----------------------------
# Step
# -----------------------------


def _fetch_source_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = inputs.get("source")

    def _err(msg: str, fp: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "file_path": fp,
            "source": src if "src" in dir() else "",
            "fetched": False,
            "error": msg,
        }, state

    if raw is None:
        return _err("source is required")

    src = str(raw).strip()
    if not src:
        return _err("source must not be empty")

    overwrite: bool = bool(params.get("overwrite", False))
    scheme = (urlparse(src).scheme or "").lower()

    # --------------------------------------------------
    # Local file path (no recognised remote scheme)
    # --------------------------------------------------
    if scheme not in _REMOTE_SCHEMES:
        local = Path(src)
        if not local.is_file():
            return {
                "file_path": str(local),
                "source": src,
                "fetched": False,
                "error": f"File not found: {src}",
            }, state
        return {
            "file_path": str(local.resolve()),
            "source": src,
            "fetched": False,
            "error": "",
        }, state

    # --------------------------------------------------
    # Remote source — resolve save_dir
    # --------------------------------------------------
    save_dir_raw = str(params.get("save_dir") or "").strip()
    if not save_dir_raw:
        return {
            "file_path": "",
            "source": src,
            "fetched": False,
            "error": "param 'save_dir' is required for remote sources",
        }, state

    save_dir = Path(save_dir_raw)
    dest = save_dir / _filename_from_url(src)

    # Cache hit — skip re-download
    if dest.is_file() and not overwrite:
        return {
            "file_path": str(dest.resolve()),
            "source": src,
            "fetched": False,
            "error": "",
        }, state

    # Fetch
    try:
        if scheme in _HTTP_SCHEMES:
            _fetch_http(src, dest)
        elif scheme in _FTP_SCHEMES:
            _fetch_ftp(src, dest)
        else:
            return {
                "file_path": "",
                "source": src,
                "fetched": False,
                "error": f"Unsupported scheme: {scheme!r}",
            }, state
    except Exception as exc:
        return {
            "file_path": "",
            "source": src,
            "fetched": False,
            "error": str(exc),
        }, state

    return {
        "file_path": str(dest.resolve()),
        "source": src,
        "fetched": True,
        "error": "",
    }, state


# -----------------------------
# Registration
# -----------------------------


def register_fetch_source() -> None:
    register_unit(
        UnitSpec(
            type_name="FetchSource",
            input_ports=FETCH_SOURCE_INPUT_PORTS,
            output_ports=FETCH_SOURCE_OUTPUT_PORTS,
            step_fn=_fetch_source_step,
            environment_tags_are_agnostic=True,
            description=(
                "Unified source resolver: verifies local file paths or downloads "
                "remote URLs (http/https/ftp) to save_dir. "
                "Output file_path is always a resolved local path."
            ),
        )
    )


__all__ = [
    "register_fetch_source",
    "FETCH_SOURCE_INPUT_PORTS",
    "FETCH_SOURCE_OUTPUT_PORTS",
]
