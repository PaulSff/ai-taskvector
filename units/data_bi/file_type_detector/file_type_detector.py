"""
FileTypeDetector unit: classify a file for mydata / pipeline routing using :mod:`rag.content_types.registry`.

Input ``data``: **file path** only — ``str`` or ``os.PathLike`` (e.g. :class:`pathlib.Path`). The path
string is not rewritten (no ``resolve()``). For ``.json`` files, ``payload`` / ``parsed`` outputs may
include JSON loaded from that path (see :func:`rag.content_types.registry.upload_router_payload`).

Outputs: ``content_type_id``, ``json_kind``, ``suffix``, ``payload``, ``parsed`` (mirror of
``payload["parsed"]``), ``error``.
"""
from __future__ import annotations

import os
from typing import Any

from units.registry import UnitSpec, register_unit

FILE_TYPE_DETECTOR_INPUT_PORTS = [("data", "Any")]
FILE_TYPE_DETECTOR_OUTPUT_PORTS = [
    ("content_type_id", "str"),
    ("json_kind", "str"),
    ("suffix", "str"),
    ("payload", "Any"),
    ("parsed", "Any"),
    ("error", "str"),
]


def _file_type_detector_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from rag.content_types.registry import upload_router_payload

    raw = inputs.get("data")
    err = ""
    fp = ""
    if raw is None:
        err = "FileTypeDetector: data is required (file path as str or os.PathLike)"
    elif isinstance(raw, str):
        fp = raw.strip()
    elif isinstance(raw, os.PathLike):
        fp = str(os.fspath(raw)).strip()
    else:
        err = f"FileTypeDetector: data must be a file path (str or os.PathLike), not {type(raw).__name__}"

    payload: dict[str, Any]
    try:
        if err:
            payload = {
                "file_path": fp,
                "suffix": "",
                "parsed": None,
                "json_kind": "",
                "content_type_id": "",
            }
        else:
            payload = upload_router_payload(file_path=fp, parsed_json=None)
    except Exception as e:
        err = (err + "; " if err else "") + str(e)
        payload = {
            "file_path": fp,
            "suffix": "",
            "parsed": None,
            "json_kind": "",
            "content_type_id": "",
        }
    parsed_out: Any = payload.get("parsed")
    return {
        "content_type_id": str(payload.get("content_type_id") or ""),
        "json_kind": str(payload.get("json_kind") or ""),
        "suffix": str(payload.get("suffix") or ""),
        "payload": payload,
        "parsed": parsed_out,
        "error": err,
    }, state


def register_file_type_detector() -> None:
    register_unit(
        UnitSpec(
            type_name="FileTypeDetector",
            input_ports=FILE_TYPE_DETECTOR_INPUT_PORTS,
            output_ports=FILE_TYPE_DETECTOR_OUTPUT_PORTS,
            step_fn=_file_type_detector_step,
            description="Registry-based file detection: input data is a file path (str or PathLike); payload from upload_router_payload; parsed mirrors payload.parsed.",
        )
    )


__all__ = [
    "register_file_type_detector",
    "FILE_TYPE_DETECTOR_INPUT_PORTS",
    "FILE_TYPE_DETECTOR_OUTPUT_PORTS",
]
