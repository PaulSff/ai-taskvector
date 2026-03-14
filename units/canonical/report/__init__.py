"""Report unit: write report file from ProcessAgent report payload."""
from units.canonical.report.report import (
    REPORT_INPUT_PORTS,
    REPORT_OUTPUT_PORTS,
    register_report,
)

__all__ = [
    "register_report",
    "REPORT_INPUT_PORTS",
    "REPORT_OUTPUT_PORTS",
]
