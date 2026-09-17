
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from agents.tools.registry import register_tool
from agents.tools.report import run_report_follow_up
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.primitives import Data


class ReportActionBlock(
    ActionBlock[Literal["report"]]
):
    """Generate a structured report and save it as a file."""

    output_format: Literal["md", "csv"]
    text: Data
    file_name: str
    output_dir: str | None = None

    @field_validator("file_name", "output_dir")
    @classmethod
    def validate_paths(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value

    @model_validator(mode="after")
    def validate_text(self) -> ReportActionBlock:
        if self.output_format == "md":
            self._validate_markdown_text()
        elif self.output_format == "csv":
            self._validate_csv_text()

        return self

    def _validate_markdown_text(self) -> None:
        required_keys = {"title", "summary", "sections"}

        if not required_keys.issubset(self.text):
            missing = required_keys - self.text.keys()
            raise ValueError(
                f"Markdown report text is missing keys: {sorted(missing)}"
            )

        if not isinstance(self.text["sections"], list):
            raise TypeError("Markdown sections must be a list")

        for section in self.text["sections"]:
            if not isinstance(section, dict):
                raise TypeError("Each Markdown section must be an object")

            if not {"heading", "body"}.issubset(section):
                raise ValueError(
                    "Each Markdown section must contain heading and body"
                )

    def _validate_csv_text(self) -> None:
        required_keys = {"headers", "rows"}

        if not required_keys.issubset(self.text):
            missing = required_keys - self.text.keys()
            raise ValueError(
                f"CSV report text is missing keys: {sorted(missing)}"
            )

        if not isinstance(self.text["headers"], list):
            raise TypeError("CSV headers must be a list")

        if not isinstance(self.text["rows"], list):
            raise TypeError("CSV rows must be a list")

        header_count = len(self.text["headers"])

        for row in self.text["rows"]:
            if not isinstance(row, list):
                raise TypeError("Each CSV row must be a list")

            if len(row) != header_count:
                raise ValueError(
                    "Each CSV row must have the same number of values "
                    "as headers"
                )


def handle_report(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, ReportActionBlock):
        raise TypeError(
            "Expected a report action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "report",
        block.as_json_object(),
    )


def register_report_tool() -> None:
    register_tool(
        "report",
        run_report_follow_up,
        action_blocks={
            "report": ReportActionBlock,
        },
        action_handlers={
            "report": handle_report,
        },
    )


register_report_tool()
