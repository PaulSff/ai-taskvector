"""Clone-role follow-up: create a new role through the clone-role workflow."""

from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import TypeAdapter, ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import (
    FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP,
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)
from core.schemas.primitives import JsonValue

EXECUTION_TIMEOUT_S: float = 60.0


def _empty_clone_role_contribution(
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    from agents.tools.clone_role.follow_ups import (
        CLONE_ROLE_FOLLOW_UP_PREFIX,
        CLONE_ROLE_FOLLOW_UP_SUFFIX,
    )

    language = language_hint()

    return FollowUpContribution(
        context_chunks=[
            CLONE_ROLE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + CLONE_ROLE_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        ],
        any_empty_tool=True,
        extra={FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP: True},
    )


def _extract_clone_role_result(out: object) -> str:
    """Extract the clone-role result from workflow output."""

    if not isinstance(out, Mapping):
        return ""

    clone_output = out.get("clone_role", out)

    if not isinstance(clone_output, Mapping):
        return str(clone_output or "").strip()

    data = clone_output.get("data", clone_output)

    if isinstance(data, Mapping):
        if data.get("ok") is True:
            return str(dict(data)).strip()

        return str(
            data.get("error")
            or data.get("message")
            or clone_output.get("error")
            or ""
        ).strip()

    return str(data or "").strip()


def _safe_set_inline_status(
    ctx: ExecutionFollowUpContext,
    status: str,
) -> None:
    try:
        ctx.set_inline_status(status)
    except (AttributeError, TypeError):
        pass


async def _safe_toast(
    ctx: ExecutionFollowUpContext,
    message: str,
) -> None:
    try:
        if ctx.is_current_run(ctx.token):
            await ctx.toast(message)
    except (AttributeError, TypeError, IndexError):
        pass


async def run_clone_role_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep these imports local to avoid tool-registration import cycles.
    from agents.chat.agent_workflow import (
        CLONE_ROLE_WORKFLOW_PATH,
        run_workflow_with_errors,
    )
    from agents.tools.clone_role.action_block import CloneRoleActionBlock
    from agents.tools.clone_role.follow_ups import (
        CLONE_ROLE_FOLLOW_UP_PREFIX,
        CLONE_ROLE_FOLLOW_UP_SUFFIX,
    )

    _safe_set_inline_status(ctx, "Cloning the Analyst…")

    try:
        clone_role_actions = po.actions.get_tool_actions("clone_role")

        if not clone_role_actions:
            raise ValueError(
                "Clone-role follow-up was requested, but no "
                "clone_role action was found"
            )

        if len(clone_role_actions) != 1:
            raise ValueError(
                "Expected exactly one clone_role action, "
                f"got {len(clone_role_actions)}"
            )

        raw_action = clone_role_actions[0]

        try:
            action = CloneRoleActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            raise ValueError(
                "Invalid clone_role action block: "
                f"{raw_action!r}; errors={exc.errors()!r}"
            ) from exc

        # Use the action block's canonical serializer so the workflow receives
        # the normalized action shape.
        action_obj = TypeAdapter(dict[str, JsonValue]).validate_json(
            json.dumps(action.as_json_object())
        )

        print(
            "clone_role_follow_up: executing action",
            {
                "new_role_name": action_obj.get("new_role_name"),
                "character_name": action_obj.get("character_name"),
            },
            flush=True,
        )

        out, errs = await run_workflow_with_errors(
            CLONE_ROLE_WORKFLOW_PATH,
            initial_inputs={
                "inject_action": {
                    "template": action_obj,
                }
            },
            unit_param_overrides=None,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            print(
                "clone_role_follow_up: workflow errors",
                {"errors": errs},
                flush=True,
            )
            await _safe_toast(
                ctx,
                f"Clone role error: {errs[0][1][:120]}",
            )

        result = _extract_clone_role_result(out)

        if not result:
            print(
                "clone_role_follow_up: returning empty tool result",
                flush=True,
            )
            return _empty_clone_role_contribution(language_hint)

        language = language_hint()

        print(
            "clone_role_follow_up: returning non-empty context chunk",
            flush=True,
        )

        return FollowUpContribution(
            context_chunks=[
                CLONE_ROLE_FOLLOW_UP_PREFIX
                + result
                + CLONE_ROLE_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            ],
            any_empty_tool=False,
            extra={FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP: True},
        )

    except TimeoutError:
        await _safe_toast(ctx, "Clone-role operation timed out")
        return _empty_clone_role_contribution(language_hint)

    except ValidationError as exc:
        await _safe_toast(
            ctx,
            f"Invalid clone-role action: {str(exc)[:120]}",
        )
        raise

    except (KeyError, TypeError, ValueError, IndexError) as exc:
        print(
            "clone_role_follow_up: crashed",
            {
                "type": type(exc).__name__,
                "message": str(exc)[:300],
            },
            flush=True,
        )

        await _safe_toast(
            ctx,
            "Clone-role workflow crashed: "
            f"{type(exc).__name__}: {str(exc)[:120]}",
        )
        raise


__all__ = ["run_clone_role_follow_up"]
