"""
JSON classification for RAG: identify workflow/catalogue/library by structure (pattern-based).

Used to decide how a .json file in mydata is indexed: n8n workflow, Node-RED workflow,
canonical process graph, Node-RED catalogue, Node-RED library, or generic (not indexed). Path is not used.

Workflow distinction (n8n vs Node-RED vs canonical, both n8n and canonical can have "connections"):
  - n8n: dict with "nodes" (list) AND "connections" (dict). n8n stores connections as an object.
  - Canonical: dict with "units" (list) AND "connections" (list). ProcessGraph shape (id, type per unit).
  - Node-RED: dict with "nodes" or "flows"; connections if present are typically array; else → node_red.

Pattern rules (order of checks):
  - dict: n8n → node_red_catalogue → canonical → node_red flow (nodes/flows/flow + optional readme/summary)
  - list: node_red flow
  - else → generic (not indexed)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _looks_like_n8n(data: dict) -> bool:
    """Structure heuristic: n8n workflow has nodes (list) and connections (dict)."""
    return isinstance(data.get("nodes"), list) and isinstance(data.get("connections"), dict)


def _looks_like_node_red_catalogue(data: dict) -> bool:
    """Structure heuristic: Node-RED catalogue has top-level 'modules' list."""
    mods = data.get("modules")
    return isinstance(mods, list) and len(mods) > 0 and isinstance(mods[0], dict)


def _looks_like_canonical_graph(data: dict) -> bool:
    """Structure heuristic: canonical process graph has 'units' (list) and 'connections' (list); units have id/type."""
    units = data.get("units")
    connections = data.get("connections")
    if not isinstance(units, list) or not isinstance(connections, list):
        return False
    if len(units) == 0:
        return True
    first = units[0]
    return isinstance(first, dict) and "id" in first and "type" in first


def _looks_like_node_red_flow(data: dict | list) -> bool:
    """Structure heuristic: Node-RED flow = list of nodes or dict with nodes/flows/flow (library wrapper)."""
    if isinstance(data, list):
        return len(data) > 0 and isinstance(data[0], dict) and ("type" in data[0] or "id" in data[0])
    if isinstance(data, dict):
        if "nodes" in data or "flows" in data:
            return True
        # Library wrapper: single flow in "flow" key (same thing, extra readme/summary)
        if "flow" in data and isinstance(data.get("flow"), list) and len(data["flow"]) > 0:
            first = data["flow"][0]
            if isinstance(first, dict) and ("type" in first or "id" in first):
                return True
    return False


def classify_json_for_rag(path: Path, data: dict | list | None) -> str:
    """
    Classify JSON for RAG extraction by structure only (path is ignored).
    Returns one of: "n8n" | "node_red" | "node_red_catalogue" | "canonical" | "generic"
    """
    if data is None:
        return "generic"
    if isinstance(data, dict):
        if _looks_like_n8n(data):
            return "n8n"
        if _looks_like_node_red_catalogue(data):
            return "node_red_catalogue"
        if _looks_like_canonical_graph(data):
            return "canonical"
        if _looks_like_node_red_flow(data):
            return "node_red"
    if isinstance(data, list):
        if _looks_like_node_red_flow(data):
            return "node_red"
    return "generic"
