from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from agents.tools.formulas_calc import run_formulas_calc_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class FormulasCalcInputs(BaseModel):
    """Workbook input cells and their values."""

    model_config = ConfigDict(
        extra="allow",
        strict=True,
    )

    @field_validator("*")
    @classmethod
    def validate_input_value(cls, value: Any) -> Any:
        return value


class FormulasCalcActionBlock(
    ActionBlock[Literal["formulas_calc"]]
):
    """Recalculate an XLSX workbook and read output cells."""

    method: Literal["calculate"] = "calculate"
    path: str
    inputs: dict[str, Any]
    outputs: list[str]
    output_format: Literal["json"]

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("path must not be empty")

        if not value.lower().endswith(".xlsx"):
            raise ValueError("path must reference an .xlsx workbook")

        return value

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        normalized_inputs: dict[str, Any] = {}

        for cell_reference, cell_value in value.items():
            cell_reference = cell_reference.strip()

            if not cell_reference:
                raise ValueError("input cell references must not be empty")

            normalized_inputs[cell_reference] = cell_value

        return normalized_inputs

    @field_validator("outputs")
    @classmethod
    def validate_outputs(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("outputs must not be empty")

        normalized_outputs: list[str] = []

        for output in value:
            output = output.strip()

            if not output:
                raise ValueError("output cell references must not be empty")

            normalized_outputs.append(output)

        return normalized_outputs


def handle_formulas_calc(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, FormulasCalcActionBlock):
        raise TypeError(
            "Expected a formulas_calc action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "formulas_calc",
        block.as_json_object(),
    )


def register_formulas_calc_tool() -> None:
    register_tool(
        "formulas_calc",
        run_formulas_calc_follow_up,
        action_blocks={
            "formulas_calc": FormulasCalcActionBlock,
        },
        action_handlers={
            "formulas_calc": handle_formulas_calc,
        },
    )


register_formulas_calc_tool()
