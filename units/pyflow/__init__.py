"""
PyFlowBase-alike node catalog: semantics of PyFlow built-in nodes in our format.

No PyFlow package dependency. Each entry: type name, input/output ports, and a Python
code template that runs with state/inputs (same contract as pyflow_adapter). When the
assistant adds a unit with a type from this catalog, we attach the template as the
unit's code_block so the unit is "translated" into our format.

Reference: https://pyflow.readthedocs.io/en/latest/PyFlow.Packages.PyFlowBase.Nodes.html
"""

from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

# (input_ports, output_ports, code_template). Ports: list of (name, type).
# Template runs with state, inputs (dict upstream_id -> value); must return value for state[node_id].
PYFLOW_NODE_CATALOG: dict[str, dict[str, Any]] = {
    "constant": {
        "input_ports": [],
        "output_ports": [("out", "Any")],
        "code_template": (
            "# Constant: output value from params.value or 0 (runner injects params into scope)\n"
            "_result = float((params or {}).get('value', 0.0))\n"
        ),
    },
    "branch": {
        "input_ports": [("condition", "bool"), ("true", "Any"), ("false", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": (
            "# Branch: condition ? true : false (inputs: port name -> value)\n"
            "cond = inputs.get('condition', False)\n"
            "t = inputs.get('true')\n"
            "f = inputs.get('false')\n"
            "_result = t if cond else f\n"
        ),
    },
    "reroute": {
        "input_ports": [("in", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": (
            "# Reroute: pass-through input (port 'in' or first value)\n"
            "_result = inputs.get('in', next(iter(inputs.values()), 0.0)) if inputs else 0.0\n"
        ),
    },
    "makeArray": {
        "input_ports": [],  # variable; typically multiple "in" pins
        "output_ports": [("out", "list")],
        "code_template": (
            "# MakeArray: collect all inputs into a list (inputs keyed by upstream id)\n"
            "_result = list(inputs.values()) if inputs else []\n"
        ),
    },
    "makeList": {
        "input_ports": [],
        "output_ports": [("out", "list")],
        "code_template": (
            "# MakeList: same as makeArray\n"
            "_result = list(inputs.values()) if inputs else []\n"
        ),
    },
    "dictKeys": {
        "input_ports": [("in", "dict")],
        "output_ports": [("out", "list")],
        "code_template": (
            "# DictKeys: output list of keys (input port 'in' or first value)\n"
            "d = inputs.get('in', next(iter(inputs.values()), None)) if inputs else None\n"
            "_result = list(d.keys()) if isinstance(d, dict) else []\n"
        ),
    },
}


def get_pyflow_template(type_name: str) -> dict[str, Any] | None:
    """Return catalog entry for type_name (input_ports, output_ports, code_template) or None."""
    return PYFLOW_NODE_CATALOG.get(type_name)


def get_pyflow_types() -> set[str]:
    """Return set of type names in the PyFlow catalog (for add_unit translation)."""
    return set(PYFLOW_NODE_CATALOG.keys())


def register_pyflow_units() -> None:
    """Register each PyFlow catalog type as a code_block_driven UnitSpec (for ports / executor)."""
    for type_name, entry in PYFLOW_NODE_CATALOG.items():
        in_ports = entry.get("input_ports") or []
        out_ports = entry.get("output_ports") or [("out", "Any")]
        register_unit(UnitSpec(
            type_name=type_name,
            input_ports=in_ports,
            output_ports=out_ports,
            step_fn=None,
            code_block_driven=True,
            environment_tags=["pyflow"],
            description=f"PyFlowBase-alike: {type_name} (runs from code_block template).",
        ))


# Register "pyflow" as an environment so it appears in add_environment and Units Library filter
def _register_pyflow_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
        register_env_loader("pyflow", register_pyflow_units)
    except Exception:
        pass


_register_pyflow_env_loader()


__all__ = [
    "PYFLOW_NODE_CATALOG",
    "get_pyflow_template",
    "get_pyflow_types",
    "register_pyflow_units",
]
