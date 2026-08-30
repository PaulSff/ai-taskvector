"""
Load canonical pipeline workflows from JSON and merge them into a graph with interface wiring.

Pipeline type (e.g. LLMSet) maps to a workflow file. The file defines topology (units + connections)
and a pipeline_interface: observation_inputs, action_output, params_unit_id. No topology is built
in code; we import the template and wire observation_source_ids → observation_inputs,
action_output → action_target_ids, and apply params to params_unit_id.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from core.schemas.pipeline_schema import PipelineTemplate
from core.schemas.process_graph import Connection, Unit
from units.registry import get_unit_spec

_CORE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _CORE_ROOT.parent.parent


def load_pipeline_template(
    pipeline_type: str,
    base_path: Path | None = None,
) -> dict[str, object] | None:
    spec = get_unit_spec(pipeline_type)

    if not spec or not spec.pipeline or not spec.template_path:
        return None

    base = base_path or _REPO_ROOT
    path = (base / spec.template_path).resolve()

    if not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8")
        decoded = cast(object, json.loads(text))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(decoded, dict):
        return None

    try:
        template = PipelineTemplate.model_validate(decoded)
    except ValidationError:
        return None

    return {
        "units": [
            unit.model_dump(mode="python", exclude_none=True)
            for unit in template.units
        ],
        "connections": [
            connection.model_dump(
                mode="python",
                by_alias=True,
                exclude_none=True,
            )
            for connection in template.connections
        ],
        "observation_inputs": template.pipeline_interface.observation_inputs,
        "action_output": template.pipeline_interface.action_output,
        "params_unit_id": template.pipeline_interface.params_unit_id,
    }



def merge_pipeline_into_graph(
    units: list[Unit],
    connections: list[Connection],
    template: dict[str, object],
    pipeline_id: str,
    params: dict[str, object],
    observation_source_ids: list[str],
    action_target_ids: list[str],
    existing_ids: set[str] | None = None,
) -> None:
    """
    Merge a pipeline template into the current graph.

    Mutates ``units`` and ``connections`` in place.

    Template unit IDs are prefixed with ``pipeline_id``, except for the
    ``params_unit_id`` unit, which becomes ``pipeline_id``.

    Pipeline parameters, excluding observation and action IDs, are applied
    to the params unit. External wiring is added from observations to the
    template inputs and from the template output to action targets.
    """

    existing = (
        {unit.id for unit in units}
        if existing_ids is None
        else existing_ids
    )

    raw_obs_inputs = template.get("observation_inputs")

    obs_inputs: list[dict[str, object]] = []

    if isinstance(raw_obs_inputs, list):
        typed_obs_inputs = cast(list[object], raw_obs_inputs)

        obs_inputs = [
            cast(dict[str, object], item)
            for item in typed_obs_inputs
            if isinstance(item, dict)
        ]

    raw_action_out = template.get("action_output")

    action_out: dict[str, object] = (
        cast(dict[str, object], raw_action_out)
        if isinstance(raw_action_out, dict)
        else {}
    )

    raw_params_unit_id = template.get("params_unit_id")
    params_uid = (
        str(raw_params_unit_id)
        if raw_params_unit_id is not None
        else ""
    )

    raw_out_unit_id = action_out.get("unit_id")
    out_unit_id = (
        str(raw_out_unit_id)
        if raw_out_unit_id is not None
        else ""
    )

    raw_out_port = action_out.get("port")
    out_port = (
        str(raw_out_port)
        if raw_out_port is not None
        else "edits"
    )

    params_override = {
        key: value
        for key, value in params.items()
        if key not in {
            "observation_source_ids",
            "action_target_ids",
        }
    }

    raw_template_units = template.get("units")
    template_units: list[dict[str, object]] = []

    if isinstance(raw_template_units, list):
        typed_template_units = cast(list[object], raw_template_units)

        template_units = [
            cast(dict[str, object], item)
            for item in typed_template_units
            if isinstance(item, dict)
        ]

    raw_template_connections = template.get("connections")
    template_connections: list[dict[str, object]] = []

    if isinstance(raw_template_connections, list):
        typed_template_connections = cast(
            list[object],
            raw_template_connections,
        )

        template_connections = [
            cast(dict[str, object], item)
            for item in typed_template_connections
            if isinstance(item, dict)
        ]

    id_map: dict[str, str] = {}

    for raw_unit in template_units:
        raw_old_id = raw_unit.get("id")

        if raw_old_id is None:
            continue

        old_id = str(raw_old_id)

        if not old_id:
            continue

        if old_id == params_uid:
            new_id = pipeline_id
        else:
            new_id = f"{pipeline_id}_{old_id}"

        if new_id in existing:
            suffix = 1
            base_id = new_id

            while f"{base_id}_{suffix}" in existing:
                suffix += 1

            new_id = f"{base_id}_{suffix}"

        id_map[old_id] = new_id
        existing.add(new_id)

        raw_unit_params = raw_unit.get("params")

        unit_params: dict[str, object] = (
            cast(dict[str, object], raw_unit_params)
            if isinstance(raw_unit_params, dict)
            else {}
        )

        if new_id == pipeline_id:
            unit_params.update(params_override)

        unit_data = dict(raw_unit)
        unit_data["id"] = new_id
        unit_data["params"] = unit_params

        units.append(Unit.model_validate(unit_data))

    for raw_connection in template_connections:
        raw_from = raw_connection.get("from") or raw_connection.get("from_id")
        raw_to = raw_connection.get("to") or raw_connection.get("to_id")

        if raw_from is None or raw_to is None:
            continue

        from_id = id_map.get(str(raw_from), str(raw_from))
        to_id = id_map.get(str(raw_to), str(raw_to))

        if from_id not in existing or to_id not in existing:
            continue

        raw_from_port = raw_connection.get("from_port")
        raw_to_port = raw_connection.get("to_port")
        raw_connection_type = raw_connection.get("connection_type")

        connections.append(
            Connection.model_validate(
                {
                    "from": from_id,
                    "to": to_id,
                    "from_port": (
                        str(raw_from_port)
                        if raw_from_port is not None
                        else "0"
                    ),
                    "to_port": (
                        str(raw_to_port)
                        if raw_to_port is not None
                        else "0"
                    ),
                    "connection_type": (
                        str(raw_connection_type)
                        if raw_connection_type is not None
                        else "direct"
                    ),
                }
            )
        )

    for index, source_id in enumerate(observation_source_ids):
        if index >= len(obs_inputs) or source_id not in existing:
            continue

        observation_input = obs_inputs[index]

        raw_template_unit_id = observation_input.get("unit_id")
        template_unit_id = (
            str(raw_template_unit_id)
            if raw_template_unit_id is not None
            else ""
        )

        target_id = id_map.get(template_unit_id, template_unit_id)

        raw_target_port = observation_input.get("port")
        target_port = (
            str(raw_target_port)
            if raw_target_port is not None
            else str(index)
        )

        if target_id not in existing:
            continue

        connections.append(
            Connection.model_validate(
                {
                    "from": source_id,
                    "to": target_id,
                    "from_port": "0",
                    "to_port": target_port,
                    "connection_type": "direct",
                }
            )
        )

    mapped_output_id = id_map.get(out_unit_id, out_unit_id)

    if mapped_output_id not in existing:
        return

    for target_id in action_target_ids:
        if target_id not in existing:
            continue

        connections.append(
            Connection.model_validate(
                {
                    "from": mapped_output_id,
                    "to": target_id,
                    "from_port": out_port,
                    "to_port": "0",
                    "connection_type": "direct",
                }
            )
        )
