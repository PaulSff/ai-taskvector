"""
Report unit: write a report file from parsed LLM output (report action).

The ProcessAgent parses the LLM response and may produce parser_output["report"]
with payload: { "output_format": "md" | "csv", "text": {...}, "file_name": "<my_report" }. Unit only uses text and output_format.
This unit takes that payload, renders "report" to Markdown or CSV, and writes output_dir/report.md
or output_dir/report.csv. No LLM call — the LLMAgent and ProcessAgent have already run.

{
  "action": "report",
  "output_format": "md",
  "file_name": "report_tool_test.md",
  "output_dir": "/output",
  "text": {
    "title": "Report Tool Verification",
    "summary": "Example report.",
    "sections": []
  }
}

"""
from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any

from core.schemas.primitives import Data, Output
from services.logging import setup_colored_logging
from units.registry import UnitSpec, register_unit

REPORT_INPUT_PORTS = [("parser_output", "Any")]
REPORT_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

logger = setup_colored_logging(logging.DEBUG)


def _unwrap_report_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    # Direct report action.
    if value.get("action") == "report":
        return value

    # Possible Inject output:
    # {"template": {"action": "report", ...}}
    template = value.get("template")
    if isinstance(template, dict) and template.get("action") == "report":
        return template

    # Possible unit-output wrapper:
    # {"data": {"action": "report", ...}}
    data = value.get("data")
    if isinstance(data, dict) and data.get("action") == "report":
        return data

    # Possible nested Inject wrapper:
    # {"data": {"template": {"action": "report", ...}}}
    if isinstance(data, dict):
        template = data.get("template")
        if isinstance(template, dict) and template.get("action") == "report":
            return template

    return None

def _md_from_report(data: dict[str, Any]) -> str:
    """Render report JSON (title, summary, sections) to Markdown."""
    parts = []
    title = (data.get("title") or "").strip()
    if title:
        parts.append(f"# {title}\n")
    summary = (data.get("summary") or "").strip()
    if summary:
        parts.append(summary + "\n")
    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        heading = (sec.get("heading") or "").strip()
        body = (sec.get("body") or "").strip()
        if heading:
            if not heading.startswith("#"):
                heading = f"## {heading}"
            parts.append(f"\n{heading}\n")
        if body:
            parts.append(body + "\n")
    return "\n".join(parts).strip() + "\n"


def _csv_from_report(data: dict[str, Any]) -> str:
    """Render report JSON (headers, rows) to CSV."""
    headers = data.get("headers")
    rows = data.get("rows")
    if not isinstance(headers, list):
        headers = []
    if not isinstance(rows, list):
        rows = []
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if headers:
        w.writerow([str(h) for h in headers])
    for row in rows:
        if isinstance(row, list):
            w.writerow([str(c) for c in row])
        else:
            w.writerow([str(row)])
    return buf.getvalue()


def _unique_path(output_dir: Path, desired_path: Path) -> Path:
    """
    If desired_path already exists inside output_dir, append suffixes:
    <stem>_1<suffix>, <stem>_2<suffix>, ...
    """
    if desired_path.parent != output_dir:
        # Safety: force everything to stay within output_dir
        desired_path = output_dir / desired_path.name

    candidate = desired_path
    i = 1
    while candidate.exists():
        candidate = output_dir / f"{desired_path.stem}_{i}{desired_path.suffix}"
        i += 1
    return candidate


def _report_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Read, render, and write a report action."""

    out: Data = {
        "ok": False,
        "output_path": "",
        "error": None,
        "report_preview": "",
    }

    parser_output = inputs.get("parser_output")

    payload = _unwrap_report_payload(parser_output)

    if payload is None:
        received_keys = (
            list(parser_output.keys())
            if isinstance(parser_output, dict)
            else None
        )

        error = (
            "Report input shape mismatch: expected a report action directly "
            "or under data/template; "
            f"received type={type(parser_output).__name__}, "
            f"keys={received_keys}."
        )
        logger.error(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    report = payload.get("text")

    if not isinstance(report, dict):
        error = (
            "Report input shape mismatch: 'text' must be a JSON object, "
            f"received {type(report).__name__}."
        )
        logger.error(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    output_format = payload.get("output_format")

    if not isinstance(output_format, str):
        error = (
            "Report input shape mismatch: 'output_format' must be a string, "
            f"received {type(output_format).__name__}."
        )
        logger.error(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    output_format = output_format.strip().lower()

    if output_format not in ("md", "csv"):
        error = (
            "Invalid report output_format: expected 'md' or 'csv', "
            f"received {output_format!r}."
        )
        logger.error(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    file_name = payload.get("file_name")

    if not isinstance(file_name, str) or not file_name.strip():
        error = (
            "Report input shape mismatch: 'file_name' must be a "
            "non-empty string."
        )
        logger.error(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    chosen_filename = file_name.strip()

    payload_output_dir = payload.get("output_dir")
    configured_output_dir = (
        payload_output_dir
        if payload_output_dir
        else params.get("output_dir")
    )

    if not configured_output_dir:
        error = "unit param output_dir is required"
        logger.error(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    output_dir = Path(
        str(configured_output_dir).strip()
    ).expanduser().resolve()

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        error = f"cannot create output_dir {output_dir}: {exc}"
        logger.exception(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    desired_suffix = ".md" if output_format == "md" else ".csv"
    chosen_path = Path(chosen_filename)

    if chosen_path.suffix.lower() != desired_suffix:
        logger.debug(
            "Adjusting report filename extension from %r to %r",
            chosen_filename,
            desired_suffix,
        )
        chosen_filename = f"{chosen_path.stem}{desired_suffix}"

    if output_format == "md":
        report_body = _md_from_report(report)
    else:
        report_body = _csv_from_report(report)

    desired_path = output_dir / chosen_filename
    report_path = _unique_path(output_dir, desired_path)

    try:
        report_path.write_text(report_body, encoding="utf-8")
    except OSError as exc:
        error = f"cannot write report to {report_path}: {exc}"
        logger.exception(error)
        out["error"] = error
        return ({"data": out, "error": error}, state)

    out["ok"] = True
    out["output_path"] = str(report_path)
    out["report_preview"] = report_body[:500] + (
        "..." if len(report_body) > 500 else ""
    )

    logger.info(
        "File was written successfully: path=%s format=%s",
        report_path,
        output_format,
    )

    return ({"data": out, "error": None}, state)


def register_report() -> None:
    """Register the Report unit type."""
    register_unit(UnitSpec(
        type_name="Report",
        input_ports=REPORT_INPUT_PORTS,
        output_ports=REPORT_OUTPUT_PORTS,
        step_fn=_report_step,
        environment_tags=["office"],
        environment_tags_are_agnostic=False,
        description="Write report from parser_output['report'] (text + output_format) to output_dir/report.md or report.csv. No LLM; use with ProcessAgent.",
    ))


__all__ = [
    "REPORT_INPUT_PORTS",
    "REPORT_OUTPUT_PORTS",
    "register_report",
]
