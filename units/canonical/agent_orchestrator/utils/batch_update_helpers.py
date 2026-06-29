# batch_publish_helpers.py
from __future__ import annotations

from typing import Any

from .batch_update_publisher import BatchUpdatePublisher


def make_publish_in_progress(
    *,
    batch_update_publisher: BatchUpdatePublisher | None,
    get_role_id: Any,
    get_agent_display: Any,
    get_turn_id: Any,
    get_messenger: Any,
    get_follow_up_contexts: Any,
    get_graph_ref: Any,
    get_last_apply_result: Any,
    get_result: Any,
    get_content: Any,
    get_response: Any,
    get_apply_meta: Any,
    get_session_language: Any,
    get_run_output: Any,
    get_source: Any,  # typically "agent_response"
) -> Any:
    def _publish_in_progress(*, stage: str, kind: str | None) -> None:
        if batch_update_publisher is None:
            return

        result = get_result()
        content = get_content()
        response = get_response() or {}
        apply_meta = get_apply_meta() or {}

        print(
            f"[orchestrator] publish_progress endpoint={batch_update_publisher.pub_endpoint} stage={stage} batch_update:has_published={batch_update_publisher is not None}"
        )

        # Use stage for the outer wrapper; do NOT finalize.
        # The publisher should emit progress-shaped output only.

        batch_update_publisher.publish_progress(
            status={"status": stage},
            role_id=get_role_id(),
            agent_display=get_agent_display(),
            display_content=str(result.get("content_for_display") or content or ""),
            turn_id=get_turn_id(),
            source=get_source(),
            session_language=get_session_language(),
            messenger=get_messenger(),
            llm_user_message=response.get("llm_user_message"),
            llm_system_prompt=response.get("llm_system_prompt"),
            id=None,
            ts=None,
            graph=get_graph_ref(),
            parsed_edits=result.get("edits", []),
            apply_meta=apply_meta,
            follow_up_contexts=get_follow_up_contexts(),
            last_apply_result=get_last_apply_result() or {},
            run_output=get_run_output() or {},
            error=None,
        )

    return _publish_in_progress
