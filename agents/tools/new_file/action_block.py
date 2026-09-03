# agents/tools/action_blocks/new_file.py

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from agents.tools.types import ActionBlock


class NewFileSpec(BaseModel):
    """Specification for the file to create."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    output_format: str
    file_name: str
    content: str

    @field_validator("output_format", "file_name")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        # Empty content is valid when creating an empty file.
        return value


class NewFileActionBlock(
    ActionBlock[Literal["new_file"]]
):
    """Generate a new file in a specified folder."""

    output_dir: str
    file: NewFileSpec

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("output_dir must not be empty")

        return value
