from __future__ import annotations

import logging
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)
from services.logging import setup_colored_logging

logger = setup_colored_logging(logging.DEBUG)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_air_shopping_rq_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    from agents.tools.air_shopping_rq.follow_ups import (
        AIR_SHOPPING_RQ_FOLLOW_UP_PREFIX,
        AIR_SHOPPING_RQ_FOLLOW_UP_SUFFIX,
    )
    from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE

    chunk = (
        AIR_SHOPPING_RQ_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + AIR_SHOPPING_RQ_FOLLOW_UP_SUFFIX.format(
            language=hint(),
            session_language=hint(),
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
    )


def _extract_air_shopping_rq_result(out: object) -> tuple[str, str]:
    if not isinstance(out, Mapping):
        logger.warning("air_shopping_rq extractor got non-mapping out: %r", out)
        return "", ""

    prompt_output = out.get("prompt")

    system_prompt = ""

    if isinstance(prompt_output, Mapping):
        raw_system_prompt = prompt_output.get("system_prompt")
        if isinstance(raw_system_prompt, str):
            system_prompt = raw_system_prompt.strip()
        elif raw_system_prompt is not None:
            system_prompt = str(raw_system_prompt).strip()

    return system_prompt, ""


async def run_air_shopping_rq_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    from agents.chat.agent_workflow import (
        run_workflow_with_errors,
    )
    from agents.tools.air_shopping_rq.action_block import AirShoppingRQActionBlock
    from agents.tools.air_shopping_rq.follow_ups import (
        AIR_SHOPPING_RQ_FOLLOW_UP_PREFIX,
        AIR_SHOPPING_RQ_FOLLOW_UP_SUFFIX,
    )
    from core.schemas.primitives import WorkflowInputs

    try:
        ctx.set_inline_status("Processing air shopping request…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        air_shopping_actions = po.actions.get_tool_actions("air_shopping_rq")

        if not air_shopping_actions:
            raise ValueError(
                "Air-shopping-rq follow-up was requested, but no "
                "air_shopping_rq action was found"
            )

        chunks: list[str] = []

        for raw_action in air_shopping_actions:
            try:
                action = AirShoppingRQActionBlock.model_validate(raw_action)
            except ValidationError as exc:
                raise ValueError(
                    "Invalid air_shopping_rq action block: "
                    f"errors={exc.errors()!r}"
                ) from exc

            payload = TypeAdapter(JsonValue).validate_json(
                action.model_dump_json()
            )

            initial_inputs: WorkflowInputs = {
                "inject_payload": {
                    "template": payload,
                }
            }

            out, errs = await run_workflow_with_errors(
                "air_shopping_rq",
                initial_inputs=initial_inputs,
                format="dict",
                execution_timeout_s=EXECUTION_TIMEOUT_S,
            )

            if errs:
                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast("Air shopping rq workflow error")
                except (AttributeError, TypeError):
                    pass

            system_prompt, _ = _extract_air_shopping_rq_result(out)

            if system_prompt:
                chunks.append(
                    AIR_SHOPPING_RQ_FOLLOW_UP_PREFIX
                    + system_prompt
                    + AIR_SHOPPING_RQ_FOLLOW_UP_SUFFIX.format(
                        language=hint(),
                        session_language=hint(),
                    )
                )

        if not chunks:
            return _empty_air_shopping_rq_contribution(hint)

        return FollowUpContribution(
            context_chunks=chunks,
            any_empty_tool=False,
        )

    except TimeoutError:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("Air shopping rq operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_air_shopping_rq_contribution(hint)

    except ValidationError as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Invalid air_shopping_rq action: "
                    f"{str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Air shopping rq workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_air_shopping_rq_follow_up"]
