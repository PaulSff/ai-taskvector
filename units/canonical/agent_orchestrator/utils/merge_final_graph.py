import asyncio
from typing import Any

from core.graph import graph_diff, merge_graph_actions_from_diff
from gui.chat.utils.workflow_manager import import_latest_workflow_graph_async

from .graph_hasher import _graph_md5


async def _merge_latest_graph_for_final_output(
    *,
    graph_ref: list[Any],
    initial_graph_md5: str | None,
) -> Any:
    latest = await import_latest_workflow_graph_async()
    if latest.graph is None:
        print(
            "[final_graph_merge] latest graph import failed/empty; keeping existing graph."
        )
        return graph_ref[0]

    latest_graph = latest.graph
    latest_md5 = _graph_md5(latest_graph)

    if initial_graph_md5 is not None:
        if latest_md5 == initial_graph_md5:
            print(
                "[final_graph_merge] latest graph unchanged (md5 match); skipping merge."
            )
            return graph_ref[0]
        else:
            print(
                "[final_graph_merge] latest graph changed (md5 differ); merging latest + edits.",
                f"initial={initial_graph_md5} latest={latest_md5}",
            )
    else:
        print(
            "[final_graph_merge] initial_graph_md5 not provided; merging latest + edits anyway.",
            f"latest={latest_md5}",
        )

    current_graph = graph_ref[0]

    res = await asyncio.to_thread(
        merge_graph_actions_from_diff,
        prev=current_graph,
        current=latest_graph,
        graph_diff_fn=graph_diff,
    )

    if not res.get("success", False):
        return latest_graph

    return res.get("graph", latest_graph)
