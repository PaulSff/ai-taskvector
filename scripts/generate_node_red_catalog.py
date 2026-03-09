#!/usr/bin/env python3
"""
Generate units/node_red catalog from the @node-red/nodes package (optional).

Requires Node.js and npm (or pnpm). Run::

    ./scripts/install_node_red_and_generate_catalog.sh

Or manually::

    export NODE_RED_NODES_PATH=/path/to/node_modules/@node-red/nodes  # if already installed
    python scripts/generate_node_red_catalog.py

The script introspects the installed @node-red/nodes package: finds core node .js files,
extracts node type names from RED.nodes.registerType("typeName", ...), and writes
units/node_red/_catalog_generated.py. units/node_red/__init__.py uses that file when
present; otherwise the built-in hand-maintained catalog is used. No Node-RED dependency at runtime.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

NODE_RED_DIR_NAME = "node_red"
GENERATED_CATALOG_FILENAME = "_catalog_generated.py"
BUILD_DIR_NAME = ".node_red_catalog_build"
PACKAGE_NAME = "@node-red/nodes"

# Known core types: (input_count, output_count) or (input_ports, output_ports) for our format.
# 0 inputs -> [], 1 input -> [("in", "Any")]; 0 outputs -> [], 1 output -> [("out", "Any")].
_PORT_MAP: dict[str, tuple[list[tuple[str, str]], list[tuple[str, str]]]] = {
    "inject": ([], [("out", "Any")]),
    "debug": ([("in", "Any")], []),
    "function": ([("in", "Any")], [("out", "Any")]),
    "change": ([("in", "Any")], [("out", "Any")]),
    "switch": ([("in", "Any")], [("out", "Any")]),
    "split": ([("in", "Any")], [("out", "Any")]),
    "join": ([("in", "Any")], [("out", "Any")]),
    "template": ([("in", "Any")], [("out", "Any")]),
}

_CODE_TEMPLATE_BY_TYPE: dict[str, str] = {
    "function": "// Node-RED function node\nreturn msg;",
    "template": "// Mustache/Handlebars template in params.template\nreturn msg;",
}

REGISTER_TYPE_RE = re.compile(r'RED\.nodes\.registerType\s*\(\s*["\']([^"\']+)["\']', re.MULTILINE)


def get_nodes_package_path(repo_root: Path) -> Path | None:
    """Return path to @node-red/nodes package: env var, or build dir node_modules."""
    env_path = os.environ.get("NODE_RED_NODES_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if p.is_dir():
            return p
    build_dir = repo_root / "scripts" / BUILD_DIR_NAME
    node_modules = build_dir / "node_modules" / PACKAGE_NAME
    if node_modules.is_dir():
        return node_modules
    return None


def ensure_nodes_package_installed(repo_root: Path) -> Path:
    """Create build dir, npm/pnpm install @node-red/nodes, return package path."""
    build_dir = repo_root / "scripts" / BUILD_DIR_NAME
    build_dir.mkdir(parents=True, exist_ok=True)
    package_json = build_dir / "package.json"
    if not package_json.exists():
        package_json.write_text(
            '{"name": "node-red-catalog-build", "private": true}\n',
            encoding="utf-8",
        )
    node_modules = build_dir / "node_modules" / PACKAGE_NAME
    if node_modules.is_dir():
        return node_modules
    # Prefer pnpm if lockfile exists in repo; else npm
    use_pnpm = (repo_root / "pnpm-lock.yaml").exists() or (build_dir / "pnpm-lock.yaml").exists()
    cmd = ["pnpm", "add", PACKAGE_NAME] if use_pnpm else ["npm", "install", PACKAGE_NAME]
    try:
        subprocess.run(cmd, cwd=build_dir, check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Failed to install {PACKAGE_NAME}: {e}", file=sys.stderr)
        if not node_modules.is_dir():
            print("Run: npm install @node-red/nodes (or pnpm add @node-red/nodes) in scripts/.node_red_catalog_build", file=sys.stderr)
            raise SystemExit(1) from e
    return node_modules


def discover_node_types(nodes_pkg_path: Path) -> list[str]:
    """Find all .js under core/ and extract registerType("name") type names."""
    core = nodes_pkg_path / "core"
    if not core.is_dir():
        return []
    type_names: list[str] = []
    seen: set[str] = set()
    for js_path in core.rglob("*.js"):
        try:
            text = js_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in REGISTER_TYPE_RE.finditer(text):
            name = m.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                type_names.append(name)
    return sorted(type_names, key=str.lower)


def build_catalog_entries(type_names: list[str]) -> list[tuple[str, list[tuple[str, str]], list[tuple[str, str]], str]]:
    """For each type, return (type_name, input_ports, output_ports, code_template)."""
    entries: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]], str]] = []
    for name in type_names:
        in_ports, out_ports = _PORT_MAP.get(
            name,
            ([("in", "Any")], [("out", "Any")]),
        )
        code = _CODE_TEMPLATE_BY_TYPE.get(name, "")
        entries.append((name, in_ports, out_ports, code))
    return entries


def _render_catalog_entry(type_name: str, in_ports: list, out_ports: list, code_template: str) -> str:
    """Render one catalog entry as Python source."""
    if code_template:
        code_lines = [
            '        "code_template": (',
            *[f'            {repr(line + chr(10))},' for line in code_template.splitlines()],
            "        ),",
        ]
    else:
        code_lines = ['        "code_template": "",']
    lines = [
        f'    "{type_name}": {{',
        f'        "input_ports": {in_ports},',
        f'        "output_ports": {out_ports},',
        *code_lines,
        "    },",
    ]
    return "\n".join(lines)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    nodes_path = get_nodes_package_path(repo_root)
    if nodes_path is None:
        nodes_path = ensure_nodes_package_installed(repo_root)
    type_names = discover_node_types(nodes_path)
    if not type_names:
        print("No node types found. Ensure @node-red/nodes has a core/ directory.", file=sys.stderr)
        raise SystemExit(1)
    entries = build_catalog_entries(type_names)
    out_dir = repo_root / "units" / NODE_RED_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / GENERATED_CATALOG_FILENAME
    body = "\n".join(
        _render_catalog_entry(name, inp, out, code) for name, inp, out, code in entries
    )
    content = f'''"""Generated by scripts/generate_node_red_catalog.py. Do not edit by hand."""
from __future__ import annotations

from typing import Any

NODE_RED_NODE_CATALOG: dict[str, dict[str, Any]] = {{
{body}
}}
'''
    out_path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(entries)} node(s) to {out_path}", file=sys.stderr)
    print(f"Types: {', '.join(type_names[:20])}{' ...' if len(type_names) > 20 else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
