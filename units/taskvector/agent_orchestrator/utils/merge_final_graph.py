import asyncio

from agents.chat.utils.workflow_manager import import_latest_workflow_graph_async
from core.graph import graph_diff, merge_graph_actions_from_diff
from core.schemas.process_graph import ProcessGraph

from .graph_hasher import graph_md5


async def merge_latest_graph_for_final_output(
    *,
    graph_ref: list[ProcessGraph],
    initial_graph_md5: str | None,
) -> ProcessGraph | None:
    current_graph = graph_ref[0]

    latest = await import_latest_workflow_graph_async()
    latest_graph = latest.graph

    if latest_graph is None:
        print(
            "[final_graph_merge] latest graph import failed/empty; keeping existing graph."
        )
        return current_graph

    latest_md5 = graph_md5(latest_graph)

    if initial_graph_md5 is not None:
        if latest_md5 == initial_graph_md5:
            print(
                "[final_graph_merge] latest graph unchanged (md5 match); skipping merge."
            )
            return current_graph

        print(
            "[final_graph_merge] latest graph changed (md5 differ); merging latest + edits.",
            f"initial={initial_graph_md5} latest={latest_md5}",
        )
    else:
        print(
            "[final_graph_merge] initial_graph_md5 not provided; merging latest + edits anyway.",
            f"latest={latest_md5}",
        )

    # The merger accepts ProcessGraph instances, not dictionaries.
    prev_unit_count = len(latest_graph.units)
    current_unit_count = len(current_graph.units)

    # Never merge from an on-disk graph that dropped all units while the
    # in-memory graph still contains units.
    if current_unit_count > 0 and prev_unit_count == 0:
        print(
            "[final_graph_merge] latest graph has no units but in-memory graph "
            + "does; keeping in-memory graph."
        )
        return current_graph

    result = await asyncio.to_thread(
        merge_graph_actions_from_diff,
        prev=latest_graph,
        current=current_graph,
        graph_diff_fn=graph_diff,
    )

    # MergeResult is a Pydantic/model object, not a dictionary.
    if not result.success:
        print(
            "[final_graph_merge] graph merge failed; "
            + "keeping in-memory graph.",
            result.error or "",
        )
        return current_graph

    merged = result.graph

    # Guard against an unexpected merge result that removes every unit.
    if current_unit_count > 0 and not merged.units:
        print(
            "[final_graph_merge] merge would drop all units; "
            + "keeping in-memory graph."
        )
        return current_graph

    return merged
