from __future__ import annotations

from collections.abc import Callable

import agents.follow_ups as agents_follow_ups
from agents.chat.context.follow_up_context import PostEditFlags
from agents.chat.context.todo_list_manager.helpers import graph_has_any_open_tasks
from agents.prompts import (
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
)
from core.schemas.process_graph import ProcessGraph


def get_post_apply_messages(
    round_idx: int,
    *,
    flags: PostEditFlags,
    language_hint: Callable[[], str],
    graph: ProcessGraph | None,
) -> tuple[str, str] | None:
    language = language_hint()

    if round_idx == 0:
        if flags.had_import_workflow:
            return (
                WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP.format(
                    language=language,
                    session_language=language,
                ),
                WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE.format(
                    language=language,
                    session_language=language,
                ),
            )

        if flags.had_add_comment and flags.had_todo:
            return (
                WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP.format(
                    language=language,
                    session_language=language,
                ),
                WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE.format(
                    language=language,
                    session_language=language,
                ),
            )

        if flags.had_add_comment:
            return (
                WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP.format(
                    language=language,
                    session_language=language,
                ),
                WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE.format(
                    language=language,
                    session_language=language,
                ),
            )

        if flags.had_todo:
            return (
                WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
                    language=language,
                    session_language=language,
                ),
                WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
                    language=language,
                    session_language=language,
                ),
            )

        return (
            agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_INJECT.format(
                language=language,
                session_language=language,
            ),
            agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE.format(
                language=language,
                session_language=language,
            ),
        )

    if not graph_has_any_open_tasks(graph):
        return None

    return (
        WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
            language=language,
            session_language=language,
        ),
        WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
            language=language,
            session_language=language,
        ),
    )
