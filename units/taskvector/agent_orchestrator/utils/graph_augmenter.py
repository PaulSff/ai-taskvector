from __future__ import annotations

from core.schemas import ProcessGraph
from core.schemas.graph_edit_api import (
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
    GraphEdit,
)
from core.schemas.primitives import Data


async def apply_and_augment_graph(
    graph_to_apply: ProcessGraph,
    edits: list[GraphEdit],
    ctx: Data,
    graph_ref: list[ProcessGraph],
    last_apply_result_ref: list[AgentApplyWorkflowEditsResult],
) -> tuple[ProcessGraph | None, list[str], str | None]:
    from agents.chat.agent_workflow.helpers import (
        refresh_last_graph_apply_result,
        validate_graph_to_apply_inline,
    )
    from agents.chat.context.todo_list_manager import (
        augment_graph_with_client_tasks,
    )

    coding_is_allowed = bool(ctx.get("coding_is_allowed", True))
    supplements: list[str] = []

    try:
        # Validate/normalize before augmentation. The todo-list augmenter
        # expects a ProcessGraph object and accesses graph.todo_lists.
        validated_graph, v_err = (
            await validate_graph_to_apply_inline(graph_to_apply)
        )

        if v_err or validated_graph is None:
            print(
                "[apply_and_augment_graph] pre-augmentation validation failed: {v_err}"
            )
            return (
                None,
                supplements,
                v_err or "graph validation failed",
            )

        graph_to_apply = validated_graph

        # The graph is now guaranteed to be a validated ProcessGraph.
        graph_to_apply, supplements = (
            await augment_graph_with_client_tasks(
                graph_to_apply,
                edits,
                coding_is_allowed=coding_is_allowed,
            )
        )

        # Validate again because augmentation may add or modify graph data.
        validated_graph, v_err = (
            await validate_graph_to_apply_inline(graph_to_apply)
        )

        if v_err or validated_graph is None:
            print(
                "[apply_and_augment_graph] post-augmentation validation failed: {v_err}"
            )
            return (
                None,
                supplements,
                v_err or "graph validation failed",
            )

        graph_to_apply = validated_graph

    except (ValueError, TypeError) as exc:
        msg = f"validation exception: {exc!r}"
        print("[apply_and_augment_graph] validation exception:", msg)
        return None, supplements, msg

    graph_ref[0] = graph_to_apply

    prev = last_apply_result_ref[0]

    apply_result = ApplyWorkflowEditsResult(
        success=True,
        graph=graph_to_apply,
    )

    last_apply_result_ref[0] = await refresh_last_graph_apply_result(
        prev,
        apply_result,
        supplement_summary="; ".join(supplements),
    )


    return graph_to_apply, supplements, None
