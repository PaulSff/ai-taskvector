from __future__ import annotations

import asyncio
from collections.abc import Mapping

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.read_file.follow_ups import (
    REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX,
    REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FOLLOW_UP_EXTRA_READ_FILE_FOLLOW_UP,
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)
from agents.tools.workflow_path import get_tool_workflow_path
from core.schemas.primitives import JsonValue, WorkflowOutputs


def _empty_read_file_contribution(
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = (language_hint() or "English").strip() or "English"

    return FollowUpContribution(
        context_chunks=[
            REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        ],
        any_empty_tool=True,
        extra={FOLLOW_UP_EXTRA_READ_FILE_FOLLOW_UP: True},
    )


def _text_from_inner_outputs(
    inner: Mapping[str, JsonValue],
) -> str:
    """Extract formatted RAG text and document-to-text table output."""

    bits: list[str] = []

    format_rag = inner.get("format_rag")
    if isinstance(format_rag, Mapping):
        data = format_rag.get("data")
        if isinstance(data, str) and data.strip():
            bits.append(data.strip())

    tables_to_text = inner.get("tables_to_text")
    if isinstance(tables_to_text, Mapping):
        text = tables_to_text.get("text")
        if isinstance(text, str) and text.strip():
            bits.append(
                "--- Tables (doc_to_text: LoadDocument → TablesToText) ---\n"
                + text.strip()
            )

    if not bits:
        prompt = inner.get("prompt")
        if isinstance(prompt, Mapping):
            system_prompt = prompt.get("system_prompt")
            if isinstance(system_prompt, str) and system_prompt.strip():
                bits.append(system_prompt.strip())

    return "\n\n".join(bits)


def _text_from_read_file_workflow_outputs(
    outputs: WorkflowOutputs,
    slot_name: str = "rw_run",
) -> str:
    slot = outputs.get(slot_name)

    if not isinstance(slot, Mapping):
        return ""

    error = slot.get("error")
    if isinstance(error, str) and error.strip():
        return ""

    inner = slot.get("data")
    if not isinstance(inner, Mapping):
        return ""

    return _text_from_inner_outputs(inner).strip()


def _run_read_file_workflow_for_path(path: str) -> str:
    """Run the read_file workflow for one validated path."""

    path = path.strip()

    if not path:
        return ""

    from runtime.run import run_workflow

    workflow_path = get_tool_workflow_path("read_file")

    if not workflow_path.is_file():
        return ""

    output = run_workflow(
        workflow_path,
        initial_inputs={
            "inject_path": {
                "data": path,
            }
        },
        format="dict",
    )

    if not isinstance(output, Mapping):
        return ""

    return _text_from_read_file_workflow_outputs(output)


def _get_read_file_actions(po: ParserOutput) -> list[str]:
    """Validate and return all read_file paths from parser output."""

    from agents.tools.read_file.action_block import ReadFileActionBlock

    actions = po.actions.get_tool_actions("read_file")

    if not actions:
        raise ValueError(
            "read_file follow-up was requested, but no read_file action was found"
        )

    paths: list[str] = []

    for raw_action in actions:
        action = ReadFileActionBlock.model_validate(raw_action)
        path = action.path.strip()

        if path:
            paths.append(path)

    return paths


async def run_read_file_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """
    Build follow-up context for one or more validated read_file actions.

    Each action has the form:

        {"path": "..."}

    Each workflow receives:

        {"inject_path": {"data": "..."}}
    """

    try:
        ctx.set_inline_status("Reading files…")
    except (AttributeError, TypeError):
        pass

    try:
        paths = _get_read_file_actions(po)

        if not paths:
            return _empty_read_file_contribution(language_hint)

        results = await asyncio.gather(
            *(
                asyncio.to_thread(
                    _run_read_file_workflow_for_path,
                    path,
                )
                for path in paths
            )
        )

        language = (language_hint() or "English").strip() or "English"
        context_chunks: list[str] = []
        had_empty_result = False

        for path, block in zip(paths, results, strict=True):
            if not block:
                had_empty_result = True
                continue

            context_chunks.append(
                REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
                + f"--- {path} ---\n"
                + block
                + REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            )

        if not context_chunks:
            return _empty_read_file_contribution(language_hint)

        return FollowUpContribution(
            context_chunks=context_chunks,
            any_empty_tool=had_empty_result,
            extra={FOLLOW_UP_EXTRA_READ_FILE_FOLLOW_UP: True},
        )

    except (
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    f"read_file failed: {str(exc)[:160]}"
                )
        except (AttributeError, TypeError, IndexError):
            pass

        return _empty_read_file_contribution(language_hint)


__all__ = ["run_read_file_follow_up"]
