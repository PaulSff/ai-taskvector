"""
Function unit: any code attached via code_block runs in the executor.

This unit has no built-in logic; it runs the source from the graph's code_blocks
(keyed by unit id), in any language declared on the code_block. Same contract as
PyFlow adapter: state, inputs (port name -> value), return value becomes the unit
output. Used for custom logic and for PyFlow-style nodes stored as type + code_block.
Env-agnostic: available for both canonical and external runtimes.
"""

from units.registry import UnitSpec, register_unit

FUNCTION_INPUT_PORTS = [("in", "Any")]
FUNCTION_OUTPUT_PORTS = [("out", "Any")]


def register_function() -> None:
    register_unit(UnitSpec(
        type_name="function",
        input_ports=FUNCTION_INPUT_PORTS,
        output_ports=FUNCTION_OUTPUT_PORTS,
        step_fn=None,
        code_block_driven=True,
        environment_tags=["canonical"],
        environment_tags_are_agnostic=True,
        runtime_scope=None,  # available for both canonical and external (e.g. PyFlow) runtimes
        description="Runs the unit's code_block (any language) with state/inputs; result is the output.",
        library_docs_path="units/CREATING-NEW-UNIT.md",
    ))


__all__ = ["register_function", "FUNCTION_INPUT_PORTS", "FUNCTION_OUTPUT_PORTS"]
