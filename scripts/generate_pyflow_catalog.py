#!/usr/bin/env python3
"""
Generate units/pyflow catalog entries from the PyFlowBase package (optional).

Run only when PyFlow is installed::

    pip install PyFlow   # or install from GitHub
    python scripts/generate_pyflow_catalog.py

The script introspects PyFlow.Packages.PyFlowBase.Nodes, lists node classes,
and outputs catalog entries (type name, input_ports, output_ports, code_template)
you can merge into units/pyflow/__init__.py. No PyFlow dependency at runtime;
this is a one-off or rare generation step.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path


def discover_pyflow_nodes() -> list[tuple[str, type]]:
    """Import PyFlow.Packages.PyFlowBase.Nodes and return [(node_type_name, node_class), ...]."""
    try:
        import PyFlow.Packages.PyFlowBase.Nodes as nodes_pkg
    except ImportError as e:
        print("PyFlow is not installed. Install with: pip install PyFlow", file=sys.stderr)
        raise SystemExit(1) from e

    result: list[tuple[str, type]] = []
    for name in dir(nodes_pkg):
        if name.startswith("_"):
            continue
        obj = getattr(nodes_pkg, name)
        if inspect.ismodule(obj):
            # Each node is often in a submodule (e.g. constant.constant)
            for subname in dir(obj):
                if subname.startswith("_"):
                    continue
                sub = getattr(obj, subname)
                if inspect.isclass(sub) and hasattr(sub, "compute"):
                    result.append((subname, sub))
        elif inspect.isclass(obj) and hasattr(obj, "compute"):
            result.append((name, obj))
    return result


def get_pins_from_class(cls: type) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Try to get input_ports and output_ports from a PyFlow node class (pins created in __init__)."""
    in_ports: list[tuple[str, str]] = []
    out_ports: list[tuple[str, str]] = []
    try:
        for name, pin in inspect.getmembers(cls, lambda x: hasattr(x, "direction")):
            if not hasattr(pin, "name"):
                continue
            pin_name = getattr(pin, "name", name)
            direction = getattr(pin, "direction", None)
            if direction is not None:
                direction_str = str(direction).split(".")[-1].lower()
                if "input" in direction_str or direction_str == "0":
                    in_ports.append((pin_name, "Any"))
                elif "output" in direction_str or direction_str == "1":
                    out_ports.append((pin_name, "Any"))
    except Exception:
        pass
    if not out_ports:
        out_ports = [("out", "Any")]
    return in_ports, out_ports


def get_compute_source(cls: type) -> str | None:
    """Get compute() method source if available."""
    if not hasattr(cls, "compute"):
        return None
    try:
        return inspect.getsource(cls.compute)
    except (TypeError, OSError):
        return None


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    nodes = discover_pyflow_nodes()
    print(f"# Found {len(nodes)} node class(es) in PyFlow.Packages.PyFlowBase.Nodes\n")
    print("# Paste or merge the entries below into units/pyflow/__init__.py PYFLOW_NODE_CATALOG\n")

    for type_name, cls in sorted(nodes, key=lambda x: x[0].lower()):
        in_ports, out_ports = get_pins_from_class(cls)
        compute_src = get_compute_source(cls)
        # Build a minimal code_template: either placeholder or simplified from compute()
        if compute_src and "getData" in compute_src:
            code_template = (
                "# Generated from PyFlow compute(); adapt to state/inputs/params API\n"
                "# Original used pin.getData(); replace with inputs[port_name] or state[node_id]\n"
                "_result = 0.0  # TODO: adapt from compute()\n"
            )
        else:
            code_template = (
                "# PyFlowBase node: adapt to state/inputs/params; return _result\n"
                "_result = next(iter(inputs.values()), 0.0) if inputs else 0.0\n"
            )

        print(f'    "{type_name}": {{')
        print(f'        "input_ports": {in_ports},')
        print(f'        "output_ports": {out_ports},')
        print(f'        "code_template": (')
        for line in code_template.splitlines():
            print(f'            {repr(line + chr(10))},')
        print(f'        ),')
        print(f'    }},\n')


if __name__ == "__main__":
    main()
