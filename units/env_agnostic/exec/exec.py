"""
Exec unit: runs a bash/shell script from the unit's code_block.

Same idea as the function unit but for shell scripts. The code_block (language: shell or bash)
is executed in our runtime via subprocess; result is the script stdout. Env-agnostic: available
for all runtimes (canonical and external); when exported to Node-RED/n8n, maps to exec node.
"""

from units.registry import UnitSpec, register_unit

EXEC_INPUT_PORTS = [("in", "Any")]
EXEC_OUTPUT_PORTS = [("out", "Any")]


def register_exec() -> None:
    register_unit(UnitSpec(
        type_name="exec",
        input_ports=EXEC_INPUT_PORTS,
        output_ports=EXEC_OUTPUT_PORTS,
        step_fn=None,
        code_block_driven=True,
        environment_tags=["canonical"],
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Runs the unit's code_block as a bash/shell script; stdout becomes the output.",
        library_docs_path="units/CREATING-NEW-UNIT.md",
    ))


__all__ = ["register_exec", "EXEC_INPUT_PORTS", "EXEC_OUTPUT_PORTS"]
