# hooks/on_apply.py
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable


async def on_apply_hook(
    *,
    token: int,
    inner_msg: dict[str, Any],
    page: Any,
    is_current_run: Callable[[int], bool],
    toast: Callable[[Any, str], Awaitable[None]],
    validate_graph_inline: Callable[[dict[str, Any]], Awaitable[tuple[Any, Any]]],
    safe_page_update: Callable[[Any], None],
    scroll_chat_to_bottom: Callable[
        [], Awaitable[None]
    ],  # not used here; included if we later need it
    apply_fn_from_agent: Any,  # apply_from_agent
    set_graph: Callable[[Any], None] | None,  # set_graph
    state: dict[str, Any],
) -> None:
    if not is_current_run(token):
        return

    try:
        graph_to_apply = inner_msg.get("graph")
        if graph_to_apply is None:
            return

        # de-dupe by content
        graph_key = json.dumps(graph_to_apply, sort_keys=True, default=str)
        if graph_key == state["last_graph_to_apply"]:
            return
        state["last_graph_to_apply"] = graph_key

        apply_fn = apply_fn_from_agent if apply_fn_from_agent is not None else set_graph
        if apply_fn is None:
            return

        # validate graph by running the workflow inline
        pg, v_err = await validate_graph_inline(graph_to_apply)
        if v_err or pg is None:
            state["graph_apply_error"] = (
                f"Could not validate graph: {(v_err or '')[:120]}"
            )
            await toast(page, state["graph_apply_error"])
            return

        # update canvas on every update event
        apply_fn(pg)
        state["graph_applied"] = True
        safe_page_update(page)

        if not state["is_initial_apply_done"]:
            state["is_initial_apply_done"] = True
            await toast(page, "Applied")

    except Exception as ex:
        state["graph_apply_error"] = str(ex).strip() or type(ex).__name__
        await toast(page, state["graph_apply_error"])
