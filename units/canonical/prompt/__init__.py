"""Prompt unit. See README.md for interface."""
from units.canonical.prompt.prompt import (
    PROMPT_INPUT_PORTS,
    PROMPT_OUTPUT_PORTS,
    register_prompt,
)

__all__ = ["PROMPT_INPUT_PORTS", "PROMPT_OUTPUT_PORTS", "register_prompt"]
