"""
PlainTextExtract unit: read a plain-text file and produce one RAG item.

Input ``data`` accepts:
  - a bare file path string
  - a RagDetectOrigin context envelope {file_path, parsed, origin}
  - any dict with a ``file_path`` key

``file_path`` input port takes precedence over ``data``.

Output ``items`` is a single-element list of {text, metadata} ready for RagChunkBuilder.

Params:
  - ``max_chars`` (int,  default 50 000): maximum characters to read from the file.
  - ``encoding``  (str,  default "utf-8"): file encoding.
  - ``origin``    (str,  default "plain_text"): stored in metadata.origin.
  - ``content_type`` (str,  default "text/plain"): stored in metadata.content_type.
"""

from __future__ import annotations

from pathlib import Path

from core.schemas.primitives import Data
from units.registry import UnitSpec, register_unit

PLAIN_TEXT_EXTRACT_INPUT_PORTS = [
    ("data", "object"),
    ("file_path", "str"),
]
PLAIN_TEXT_EXTRACT_OUTPUT_PORTS = [
    ("items", "list"),
    ("error", "str")
]

_DEFAULT_MAX_CHARS = 50_000
_DEFAULT_ENCODING = "utf-8"


def _resolve_path(data: object | None, file_path_port: object | None) -> str:
    if isinstance(file_path_port, str) and file_path_port.strip():
        return file_path_port.strip()
    if isinstance(data, dict):
        fp = str(data.get("file_path") or "").strip()
        if fp:
            return fp
    if isinstance(data, str) and data.strip():
        return data.strip()
    return ""


def _plain_text_extract_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
):
    try:
        fp = _resolve_path(inputs.get("data"), inputs.get("file_path"))
        if not fp:
            return {"items": [], "error": "no file_path provided"}, state

        path = Path(fp)
        if not path.is_file():
            return {"items": [], "error": f"file not found: {fp}"}, state

        raw = params.get("max_chars", _DEFAULT_MAX_CHARS)

        if isinstance(raw, (int, str, float)):
            max_chars = max(1, int(raw or _DEFAULT_MAX_CHARS))
        else:
            max_chars = _DEFAULT_MAX_CHARS

        encoding = (
            str(params.get("encoding", _DEFAULT_ENCODING)).strip() or _DEFAULT_ENCODING
        )
        origin = str(params.get("origin", "plain_text")).strip() or "plain_text"
        content_type = (
            str(params.get("content_type", "text/plain")).strip() or "text/plain"
        )

        try:
            text = path.read_text(encoding=encoding, errors="replace")
        except OSError as e:
            return {"items": [], "error": str(e)}, state

        text = text.strip()
        if not text:
            return {"items": [], "error": ""}, state

        if len(text) > max_chars:
            text = text[:max_chars]

        return {
            "items": [
                {
                    "text": text,
                    "metadata": {
                        "file_path": str(path.resolve()),
                        "origin": origin,
                        "content_type": content_type,
                    },
                }
            ],
            "error": "",
        }, state

    except (ValueError, TypeError, UnicodeError) as e:
        return {"items": [], "error": str(e)}, state


def register_plain_text_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="PlainTextExtract",
            input_ports=PLAIN_TEXT_EXTRACT_INPUT_PORTS,
            output_ports=PLAIN_TEXT_EXTRACT_OUTPUT_PORTS,
            step_fn=_plain_text_extract_step,
            environment_tags=["rag"],
            environment_tags_are_agnostic=False,
            description=(
                "Read a plain-text file and produce one RAG item {text, metadata}. "
                "Handles bare path strings and RagDetectOrigin context envelopes. "
                "Params: max_chars (50000), encoding ('utf-8'), origin ('plain_text')."
            ),
        )
    )


__all__ = [
    "PLAIN_TEXT_EXTRACT_INPUT_PORTS",
    "PLAIN_TEXT_EXTRACT_OUTPUT_PORTS",
    "register_plain_text_extract",
]
