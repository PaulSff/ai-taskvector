from __future__ import annotations

import inspect
import traceback
from collections.abc import Callable

from agents.chat.context.context_mergers import (
    merge_follow_up_contribution_into_acc,
)
from agents.chat.context.follow_up_context import (
    ParserFollowUpContext,
    WDFollowUpAcc,
)
from agents.tools.catalog import ordered_tools_for_role_id
from agents.tools.registry import get_follow_up_runner
from core.schemas.primitives import Data

from .tool_controller import (
    follow_up_tool_enabled,
)


async def run_role_ordered_follow_ups(
    ctx: ParserFollowUpContext,
    po: Data,
    response: Data,
    hint: Callable[[], str],
    acc: WDFollowUpAcc,
) -> None:
    ordered = (
        getattr(ctx, "ordered_follow_up_tools", None)
        or ordered_tools_for_role_id(ctx.agent_role_id)
    )

    for tool_id, parser_key in ordered:
        if not follow_up_tool_enabled(ctx, tool_id):
            continue

        grey = "\033[38;5;245m"
        reset = "\033[0m"

        print(
            f"{grey}"
            + "[parser_follow_up_chain] "
            + "followup_tool_enabled "
            + f"tool_id={tool_id}"
            + f"{reset}",
            flush=True,
        )

        value = po.get(parser_key)
        if not value:
            continue

        print(
            "[parser_follow_up_chain] "
            + f"gate parser_key={parser_key} "
            + f"val={type(value).__name__} "
            + f"truth={bool(value)} "
            + f"repr={repr(value)[:400]}",
            flush=True,
        )

        runner = get_follow_up_runner(tool_id)
        if runner is None:
            continue

        green = "\033[92m"
        reset = "\033[0m"

        print(
            f"{green}"
            + "[parser_follow_up_chain] "
            + "followup_runner_start "
            + f"tool_id={tool_id} "
            + f"parser_key={parser_key}"
            + f"{reset}",
            flush=True,
        )

        result = runner(
            ctx,
            po,
            language_hint=hint,
        )

        try:
            if inspect.isawaitable(result):
                print(
                    "[parser_follow_up_chain] "
                    + f"waiting tool_id={tool_id} "
                    + f"parser_key={parser_key}",
                    flush=True,
                )

                # inspect.isawaitable narrows to Awaitable[Any], so cast
                # the awaited value back to the runner's declared result.
                contrib = await result
            else:
                contrib = result

        except Exception as exc:
            print(
                "[parser_follow_up_chain] "
                + "followup_runner_await_failed "
                + f"tool_id={tool_id} "
                + f"parser_key={parser_key}: "
                + f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            traceback.print_exc()
            raise


        merge_follow_up_contribution_into_acc(acc, contrib)
