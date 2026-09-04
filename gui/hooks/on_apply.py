# hooks/on_apply.py
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from core.schemas.primitives import Data
from core.schemas.process_graph import ProcessGraph  # adjust import

GraphValidator = Callable[
    [ProcessGraph | None],
    Awaitable[tuple[ProcessGraph | None, str | None]],
]


async def on_apply_hook(
    *,
    token: int,
    inner_msg: Data,
    page: ft.Page,
    is_current_run: Callable[[int], bool],
    toast: Callable[[Any, str], Awaitable[None]],
    validate_graph_inline: GraphValidator,
    safe_page_update: Callable[[Any], None],
    scroll_chat_to_bottom: Callable[[], Awaitable[None]],
    apply_fn_from_agent: Callable[[ProcessGraph], Any] | None,
    set_graph: Callable[[ProcessGraph], None] | None,
    state: Data,
) -> None:
    if not is_current_run(token):
        return

    try:
        graph = inner_msg.get("graph")

        if graph is None:
            return

        if not isinstance(graph, ProcessGraph):
            raise TypeError(
                f"Expected graph to be ProcessGraph, got {type(graph).__name__}"
            )

        # De-dupe by graph content.
        graph_key = json.dumps(
            graph.model_dump(by_alias=True),
            sort_keys=True,
            default=str,
        )

        if graph_key == state["last_graph_to_apply"]:
            return

        state["last_graph_to_apply"] = graph_key

        apply_fn = (
            apply_fn_from_agent
            if apply_fn_from_agent is not None
            else set_graph
        )

        if apply_fn is None:
            return

        pg, v_err = await validate_graph_inline(graph)

        if v_err or pg is None:
            state["graph_apply_error"] = (
                f"Could not validate graph: {(v_err or '')[:120]}"
            )
            await toast(page, state["graph_apply_error"])
            return

        apply_fn(pg)
        state["graph_applied"] = True
        safe_page_update(page)

        await toast(page, "Applied")

    except (KeyError, TypeError, json.JSONDecodeError) as ex:
        state["graph_apply_error"] = str(ex).strip() or type(ex).__name__
        await toast(page, state["graph_apply_error"])
