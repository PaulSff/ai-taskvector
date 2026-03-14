"""
Report unit: write a report file from parsed LLM output (report action).

The ProcessAgent parses the LLM response and may produce parser_output["report"]
with payload: { "output_format": "md" | "csv", "text": {...} }. Unit only uses text and output_format.
This unit takes that payload, renders "report" to Markdown or CSV, and writes output_dir/report.md
or output_dir/report.csv. No LLM call — the LLMAgent and ProcessAgent have already run.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

REPORT_INPUT_PORTS = [("parser_output", "Any")]
REPORT_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


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


def _report_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read parser_output['report'], render report to MD/CSV, write to output_dir."""
    out: dict[str, Any] = {"ok": False, "output_path": "", "error": None, "report_preview": ""}
    parser_output = inputs.get("parser_output")
    if not isinstance(parser_output, dict):
        out["error"] = "parser_output must be a dict (from ProcessAgent)"
        return ({"data": out, "error": out["error"]}, state)
    payload = parser_output.get("report")
    if not isinstance(payload, dict):
        out["error"] = "parser_output has no report payload"
        return ({"data": out, "error": out["error"]}, state)
    report = payload.get("text")
    if not isinstance(report, dict):
        out["error"] = "report payload must contain 'text' (JSON object)"
        return ({"data": out, "error": out["error"]}, state)
    output_format = (payload.get("output_format") or "md").strip().lower()
    if output_format not in ("md", "csv"):
        output_format = "md"
    output_dir = params.get("output_dir")
    if not output_dir:
        out["error"] = "unit param output_dir is required"
        return ({"data": out, "error": out["error"]}, state)
    output_dir = Path(str(output_dir).strip()).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        out["error"] = f"cannot create output_dir: {e}"
        return ({"data": out, "error": out["error"]}, state)
    if output_format == "md":
        report_body = _md_from_report(report)
        report_path = output_dir / "report.md"
    else:
        report_body = _csv_from_report(report)
        report_path = output_dir / "report.csv"
    try:
        report_path.write_text(report_body, encoding="utf-8")
    except OSError as e:
        out["error"] = f"cannot write report: {e}"
        return ({"data": out, "error": out["error"]}, state)
    out["ok"] = True
    out["output_path"] = str(report_path)
    out["report_preview"] = report_body[:500] + ("..." if len(report_body) > 500 else "")
    return ({"data": out, "error": None}, state)


def register_report() -> None:
    """Register the Report unit type."""
    register_unit(UnitSpec(
        type_name="Report",
        input_ports=REPORT_INPUT_PORTS,
        output_ports=REPORT_OUTPUT_PORTS,
        step_fn=_report_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Write report from parser_output['report'] (text + output_format) to output_dir/report.md or report.csv. No LLM; use with ProcessAgent.",
    ))


__all__ = [
    "register_report",
    "REPORT_INPUT_PORTS",
    "REPORT_OUTPUT_PORTS",
]
