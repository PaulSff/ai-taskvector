"""
Resolve import_workflow edits to concrete replace_graph (or merge) edits.
import_workflow loads from file path or URL; resolution produces edits that apply_graph_edit can handle.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from core.graph.core_config import valid_origin
from core.normalizer.normalizer import FormatProcess, to_process_graph
from core.schemas.graph_edit_api import GraphEdit
from core.schemas.primitives import (
    JsonArray,
    JsonDocument,
    JsonObject,
    is_json_document,
)
from core.schemas.process_graph import Connection, ProcessGraph

_VALID_ORIGIN: set[str] = set(valid_origin)

def _slug_from_type(node_type: str) -> str:
    """Convert node type to a safe id slug (e.g. 'http request' -> 'http_request')."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(node_type).strip())
    return (s or "unit").strip("_").lower()


def _generate_unit_id(node_types: list[str], existing_ids: set[str]) -> str:
    """Generate a unique unit id from node type."""
    base = _slug_from_type(node_types[0]) if node_types else "unit"
    for i in range(1, 1000):
        candidate = f"{base}_{i}" if i > 1 else base
        if candidate not in existing_ids:
            return candidate
    return f"{base}_{hash(str(existing_ids)) % 10000}"


def _detect_workflow_format(
    raw: JsonObject | JsonArray,
) -> FormatProcess:
    """Detect workflow format from raw JSON structure."""
    if isinstance(raw, dict):
        if (
            "nodes" in raw
            and "links" in raw
            and raw.get("version") is not None
        ):
            return "comfyui"

        if "nodes" in raw and "connections" in raw:
            return "n8n"

        if "nodes" in raw or "flows" in raw:
            return "node_red"

    return "node_red"



def _load_workflow_source(
    source: str,
    origin: str | None = None,
) -> tuple[JsonDocument, FormatProcess] | None:
    source = source.strip()
    if not source:
        return None

    raw: object

    if source.startswith(("http://", "https://")):
        try:
            import requests
        except ImportError:
            return None

        try:
            response = requests.get(source, timeout=60)
            response.raise_for_status()

            # requests.Response.json() is typed as Any, so constrain it here.
            raw = cast(object, response.json())
        except (requests.RequestException, ValueError):
            return None

    else:
        path = Path(source).expanduser().resolve()

        if not path.is_file():
            return None

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            # json.loads() is also commonly typed as Any.
            raw = cast(object, json.loads(text))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    if not is_json_document(raw):
        return None

    if origin:
        fmt_raw = str(origin).strip().lower()

        if fmt_raw in _VALID_ORIGIN:
            if fmt_raw == "canonical":
                fmt_raw = "dict"

            return raw, cast(FormatProcess, fmt_raw)

    fmt = _detect_workflow_format(raw)
    return raw, fmt


def load_workflow_to_canonical(
    source: str,
    origin: str | None = None,
) -> tuple[JsonObject | None, str]:
    """
    Load a workflow from a file path or URL and convert it to a canonical
    graph dictionary.
    """
    source = source.strip()

    if not source:
        return None, "source is empty"

    loaded = _load_workflow_source(source, origin=origin)

    if loaded is None:
        return None, "failed to load source (file not found or invalid)"

    raw, fmt = loaded

    try:
        graph = to_process_graph(raw, format=fmt)

        if hasattr(graph, "model_dump"):
            dumped = cast(
                object,
                graph.model_dump(by_alias=True),
            )
        else:
            dumped = cast(object, dict(graph))

        if not is_json_document(dumped):
            return None, "canonical graph contains non-JSON values"

        if not isinstance(dumped, dict):
            return None, "canonical graph is not a JSON object"

        canonical: JsonObject = dumped
        return canonical, ""

    except (TypeError, ValueError) as exc:
        return None, str(exc)


def resolve_import_workflow(
    edit: GraphEdit,
    current: ProcessGraph,
) -> list[GraphEdit]:
    source = edit.source

    if not source:
        return []

    origin = edit.origin or edit.format

    loaded = _load_workflow_source(source, origin=origin)

    if not loaded:
        return []

    raw, fmt = loaded

    try:
        imported_graph = to_process_graph(raw, format=fmt)
    except (TypeError, ValueError):
        return []

    if not edit.merge:
        return [
            GraphEdit(
                action="replace_graph",
                units=[
                    unit.model_dump(mode="json")
                    for unit in imported_graph.units
                ],
                connections=[
                    connection.model_dump(mode="json")
                    for connection in imported_graph.connections
                ],
            )
        ]

    existing_ids = {unit.id for unit in current.units}

    id_map: dict[str, str] = {}
    new_units = list(imported_graph.units)

    for unit in new_units:
        old_id = unit.id

        if old_id in existing_ids or old_id in id_map.values():
            fresh_id = _generate_unit_id(
                [unit.type or "unit"],
                existing_ids | set(id_map.values()),
            )

            id_map[old_id] = fresh_id
            unit.id = fresh_id
            existing_ids.add(fresh_id)
        else:
            existing_ids.add(old_id)

    new_connections: list[Connection] = []

    for connection in imported_graph.connections:
        from_id = id_map.get(connection.from_id, connection.from_id)
        to_id = id_map.get(connection.to_id, connection.to_id)

        if from_id in existing_ids and to_id in existing_ids:
            new_connections.append(
                connection.model_copy(
                    update={
                        "from_id": from_id,
                        "to_id": to_id,
                    }
                )
            )

    return [
        GraphEdit(
            action="replace_graph",
            units=[
                unit.model_dump(mode="json")
                for unit in current.units + new_units
            ],
            connections=[
                connection.model_dump(mode="json")
                for connection in current.connections + new_connections
            ],
        )
    ]



def resolve_import_edits(
    edits: list[GraphEdit],
    current: ProcessGraph,
) -> list[GraphEdit]:
    """
    Resolve import_workflow edits to concrete GraphEdit instances.

    Non-import edits are passed through unchanged.
    """
    resolved: list[GraphEdit] = []

    for edit in edits:
        if edit.action == "import_workflow":
            sub_edits = resolve_import_workflow(edit, current)
            resolved.extend(sub_edits)
        else:
            resolved.append(edit)

    return resolved
