import asyncio
from typing import Any


async def _apply_and_augment_graph(
    graph_to_apply: Any,
    edits: list[Any],
    ctx: dict[str, Any],
    graph_ref: list[Any],
    last_apply_result_ref: list[Any],
) -> tuple[Any, list[str], str | None]:
    from gui.chat.agent_workflow.helpers import (
        refresh_last_apply_result_after_canvas_apply,
    )
    from gui.chat.context.todo_list_manager import augment_graph_with_client_tasks

    coding_is_allowed = bool(ctx.get("coding_is_allowed", True))
    supplements: list[str] = []
    v_err: str | None = None

    if isinstance(graph_to_apply, dict):
        graph_to_apply, supplements = await asyncio.to_thread(
            augment_graph_with_client_tasks,
            graph_to_apply,
            edits,
            coding_is_allowed=coding_is_allowed,
        )

        try:
            from gui.components.workflow_tab.workflows.core_workflows import (
                validate_graph_to_apply_for_canvas,
            )

            vg, v_err = await validate_graph_to_apply_for_canvas(graph_to_apply)
            if v_err or vg is None:
                graph_to_apply = None
            else:
                graph_to_apply = vg
        except Exception:
            pass

    if graph_to_apply is not None:
        graph_ref[0] = graph_to_apply
        last_apply_result_ref[0] = refresh_last_apply_result_after_canvas_apply(
            last_apply_result_ref[0],
            graph_ref[0],
            supplement_summary="; ".join(supplements),
        )

    return graph_to_apply, supplements, v_err
