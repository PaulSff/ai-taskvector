
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from agents.tools.types import ActionBlock


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
        for cell_reference in value:
            if not cell_reference.strip():
                raise ValueError("input cell references must not be empty")

        return value

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
