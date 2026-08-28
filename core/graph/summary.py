"""
LLM-friendly graph summary. No dependency on agents.
Used by ApplyEdits unit and by workflow designer / chat.
"""

from __future__ import annotations

from collections.abc import Iterable

from core.graph import core_config as cfg
from core.schemas.process_graph import (
    CodeBlock,
    Comment,
    GraphOrigin,
    ProcessGraph,
    TodoList,
    TodoTask,
    Unit,
)

type MetadataValue = object

# Graph summary caps to avoid overwhelming the LLM.
METADATA_STR_MAX: int = int(cfg.metadata_str_max)
COMMENTS_MAX: int = int(cfg.comments_max)
COMMENT_INFO_MAX: int = int(cfg.comment_info_max)
TODO_TASKS_MAX: int = int(cfg.todo_tasks_max)


def _truncate(value: str, max_len: int) -> str:
    if not value or len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _port_names_from_unit(unit: Unit) -> tuple[list[str], list[str]]:
    """Return input and output port names from a graph unit."""
    return (
        [port.name for port in unit.input_ports],
        [port.name for port in unit.output_ports],
    )


def _origin_summary(origin: GraphOrigin | None) -> dict[str, object] | None:
    """Return a compact origin summary for the LLM."""
    if origin is None or origin.node_red is None:
        return None

    return {
        "node_red": True,
        "tabs": len(origin.node_red.tabs),
    }


def _code_block_summary(
    block: CodeBlock,
    *,
    include_source: bool,
) -> dict[str, object]:
    """Summarize one code block."""
    summary: dict[str, object] = {
        "id": block.id,
        "language": block.language,
    }

    if include_source and block.source.strip():
        summary["source"] = block.source.strip()

    return summary


def _code_blocks_summary(
    blocks: Iterable[CodeBlock],
    *,
    include_code_block_source: bool = False,
    include_source_for_unit_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    """
    Summarize code blocks.

    Source is included for every block when `include_code_block_source` is true,
    or only for blocks whose IDs are included in `include_source_for_unit_ids`.
    """
    include_ids = include_source_for_unit_ids or set()

    return [
        _code_block_summary(
            block,
            include_source=(
                include_code_block_source or block.id in include_ids
            ),
        )
        for block in blocks
    ]


def _unit_summary(unit: Unit) -> dict[str, object]:
    """Create the LLM-facing summary for one unit."""
    input_ports, output_ports = _port_names_from_unit(unit)

    return {
        "id": unit.id,
        "type": unit.type,
        "controllable": unit.controllable,
        "params": dict(unit.params),
        "input_ports": input_ports,
        "output_ports": output_ports,
    }



def _comment_summary(comment: Comment) -> dict[str, object]:
    return {
        "id": comment.id,
        "info": _truncate(comment.info, COMMENT_INFO_MAX),
        "commenter": comment.commenter,
        "created_at": comment.created_at,
    }


def _todo_task_summary(task: TodoTask) -> dict[str, object]:
    return {
        "id": task.id,
        "text": task.text,
        "completed": task.completed,
        "created_at": task.created_at,
    }


def _todo_list_summary(todo_list: TodoList) -> dict[str, object]:
    return {
        "id": todo_list.id,
        "title": todo_list.title,
        "tasks": [
            _todo_task_summary(task)
            for task in todo_list.tasks[:TODO_TASKS_MAX]
        ],
    }


def _metadata_summary(
    metadata: dict[str, MetadataValue] | None,
) -> dict[str, MetadataValue] | None:
    if not metadata:
        return None

    capped: dict[str, MetadataValue] = {}

    for key, value in metadata.items():
        if value is None:
            continue

        if isinstance(value, str):
            if value.strip():
                capped[key] = _truncate(value, METADATA_STR_MAX)
        else:
            capped[key] = value

    return capped or None


def graph_summary(
    current: ProcessGraph | None,
    *,
    include_code_block_source: bool = False,
    include_source_for_unit_ids: list[str] | None = None,
    include_structure: bool = True,
) -> dict[str, object]:
    """
    Reduce graph context to a small, LLM-friendly summary.

    When `include_code_block_source` is true, source is included for every
    code block. When `include_source_for_unit_ids` is provided, source is
    included only for matching code-block IDs.

    When `include_structure` is false, units, connections, code blocks,
    metadata, and origin context are omitted. Comments and todo lists remain.
    """
    if current is None:
        return {
            "units": [],
            "connections": [],
            **({"environment_type": None} if include_structure else {}),
        }

    result: dict[str, object] = {
        "units": [],
        "connections": [],
    }

    if include_structure:
        result["units"] = [_unit_summary(unit) for unit in current.units]
        result["connections"] = [
            {
                "from": connection.from_id,
                "to": connection.to_id,
                "from_port": connection.from_port,
                "to_port": connection.to_port,
            }
            for connection in current.connections
        ]

        result["environment_type"] = current.environment_type.value

        if current.environments is not None:
            result["environments"] = current.environments

        origin = _origin_summary(current.origin)
        if origin is not None:
            result["origin"] = origin

        if current.origin_format is not None:
            result["origin_format"] = current.origin_format

        code_blocks = _code_blocks_summary(
            current.code_blocks,
            include_code_block_source=include_code_block_source,
            include_source_for_unit_ids=set(include_source_for_unit_ids or []),
        )
        if code_blocks:
            result["code_blocks"] = code_blocks

        metadata = _metadata_summary(current.metadata)
        if metadata is not None:
            result["metadata"] = metadata

    comments = current.comments or []
    if comments:
        result["comments"] = [
            _comment_summary(comment)
            for comment in comments[-COMMENTS_MAX:]
        ]

    if current.todo_lists:
        result["todo_lists"] = [
            _todo_list_summary(todo_list)
            for todo_list in current.todo_lists
        ]

    return result
