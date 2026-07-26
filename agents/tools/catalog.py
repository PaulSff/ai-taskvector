from __future__ import annotations

import functools
from pathlib import Path

import yaml

from .workflow_path import _TOOLS_ROOT

# ---- Index: tool_id -> tool.yaml path (one-time at import) ----

def _index_tool_yaml_paths_by_id() -> dict[str, Path]:
    index: dict[str, Path] = {}

    for tool_dir in _TOOLS_ROOT.iterdir():
        if not tool_dir.is_dir():
            continue

        tool_yaml = tool_dir / "tool.yaml"
        if not tool_yaml.is_file():
            continue

        data = yaml.safe_load(tool_yaml.read_text(encoding="utf-8"))

        if isinstance(data, dict) and isinstance(data.get("id"), str):
            index[data["id"]] = tool_yaml

    return index


_TOOL_ID_TO_YAML_PATH: dict[str, Path] = _index_tool_yaml_paths_by_id()

# ---- Load only the tool_ids a role needs ----

def _build_parser_key_mapping_for_tool_ids(
    tool_ids: set[str],
) -> dict[str, list[str]]:
    """
    Build tool_id -> parser_keys mapping by loading only the tool.yaml
    files for the specified tool_ids.
    """
    mapping: dict[str, list[str]] = {}
    for tid in tool_ids:
        tool_yaml = _TOOL_ID_TO_YAML_PATH.get(tid)
        if not tool_yaml:
            continue

        data = yaml.safe_load(tool_yaml.read_text(encoding="utf-8"))

        if not (isinstance(data, dict) and "parser_keys" in data):
            continue

        parser_keys = data.get("parser_keys")
        if isinstance(parser_keys, list) and all(isinstance(k, str) for k in parser_keys):
            mapping[tid] = parser_keys

    return mapping


# ---- Getters ----

def parser_keys_for_tool(tool_id: str) -> list[str] | None:
    """
    Return parser_output dict key(s) for a tool id from tool.yaml.
    Loads just this one tool.yaml.
    """
    tool_yaml = _TOOL_ID_TO_YAML_PATH.get(tool_id)
    if not tool_yaml:
        return None

    data = yaml.safe_load(tool_yaml.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        parser_keys = data.get("parser_keys")
        if isinstance(parser_keys, list) and all(isinstance(k, str) for k in parser_keys):
            return parser_keys
    return None


def tool_id_for_parser_keys(parser_key: str) -> str | None:
    """
    Note: Without scanning all tools, we can't map parser_key -> tool_id
    globally unless we build a reverse index.
    """
    # Fallback: scan only until we find the parser_key, by loading tool.yaml files on demand.
    # If you want a fully fast reverse lookup, tell me and I’ll add an indexed reverse map built once at import.
    for tid, tool_yaml in _TOOL_ID_TO_YAML_PATH.items():
        data = yaml.safe_load(tool_yaml.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            keys = data.get("parser_keys")
            if isinstance(keys, list) and parser_key in keys:
                return tid
    return None


# ---- Role-specific ordered tuples ----

@functools.cache
def _ordered_tools_for_role_id(role_id: str | None) -> tuple[tuple[str, str], ...]:
    """
    Build (tool_id, parser_key) tuples from role.yaml tools and tool.yaml parser_keys.
    Only loads parser_keys for tool_ids present in the role configuration.
    """
    from agents.roles.registry import get_role

    if role_id is None or not role_id.strip():
        return ()

    role = get_role(role_id.strip())

    # Normalize the tool ids present in this role
    role_tool_ids: set[str] = {
        str(tid).strip()
        for tid in role.tools
        if tid is not None and str(tid).strip()
    }

    parser_map = _build_parser_key_mapping_for_tool_ids(role_tool_ids)

    out: list[tuple[str, str]] = []
    for tid in role.tools:
        tid_str = str(tid).strip()
        if not tid_str:
            continue

        keys = parser_map.get(tid_str)
        if not keys:
            out.append((tid_str, tid_str))
        else:
            for k in keys:
                out.append((tid_str, k))

    return tuple(out)
