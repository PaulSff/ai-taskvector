"""
n8n built-in node catalog: core node types in our format.

No n8n runtime dependency. Each entry: type name, input/output ports, optional
JavaScript code_template for export. When the assistant adds a unit with a type from
this catalog, we attach the template as the unit's code_block (language: javascript)
so the graph is convertible to n8n format. No JS executor in-app yet; code_block
is for canonical representation and export.

Reference: https://docs.n8n.io/integrations/builtin/node-types/
"""

from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

# Type name aligns with n8n (e.g. "Code", "HTTP Request"). code_template: JS for Code node; empty for others.
N8N_NODE_CATALOG: dict[str, dict[str, Any]] = {
    "Code": {
        "input_ports": [("in", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": "// n8n Code node\nreturn items;",
    },
    "HTTP Request": {
        "input_ports": [("in", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": "",  # config: method, url, body
    },
    "Schedule Trigger": {
        "input_ports": [],
        "output_ports": [("out", "Any")],
        "code_template": "",  # config: cron/interval
    },
    "Switch": {
        "input_ports": [("in", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": "",  # config: rules
    },
    "Merge": {
        "input_ports": [("in1", "Any"), ("in2", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": "",  # config: mode
    },
    "Set": {
        "input_ports": [("in", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": "",  # config: assign values
    },
    "No Operation": {
        "input_ports": [("in", "Any")],
        "output_ports": [("out", "Any")],
        "code_template": "",  # pass-through
    },
}


def get_n8n_template(type_name: str) -> dict[str, Any] | None:
    """Return catalog entry for type_name (input_ports, output_ports, code_template) or None."""
    return N8N_NODE_CATALOG.get(type_name)


def get_n8n_types() -> set[str]:
    """Return set of type names in the n8n catalog (for add_unit → canonical + code_block)."""
    return set(N8N_NODE_CATALOG.keys())


def register_n8n_units() -> None:
    """Register each n8n catalog type as a UnitSpec (for Units Library when env=n8n)."""
    for type_name, entry in N8N_NODE_CATALOG.items():
        in_ports = entry.get("input_ports") or []
        out_ports = entry.get("output_ports") or [("out", "Any")]
        register_unit(UnitSpec(
            type_name=type_name,
            input_ports=in_ports,
            output_ports=out_ports,
            step_fn=None,
            code_block_driven=True,  # no JS executor yet; code_block for canonical/export
            environment_tags=["n8n"],
            description=f"n8n built-in: {type_name} (JS code_block for export).",
        ))


def _register_n8n_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
        register_env_loader("n8n", register_n8n_units)
    except Exception:
        pass


_register_n8n_env_loader()


__all__ = [
    "N8N_NODE_CATALOG",
    "get_n8n_template",
    "get_n8n_types",
    "register_n8n_units",
]
