# batch_update_publisher.py
from __future__ import annotations

import time
from collections.abc import Mapping

from agents.chat.context.follow_up_context import FollowUpContexts
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult, GraphEdit
from core.schemas.primitives import Data, JsonObject
from core.schemas.process_graph import ProcessGraph
from services.zmq.zmq_messaging import ZmqPublisher, ZmqTopics


class BatchUpdatePublisher:
    """
    Publishes payloads to the framework's "update_batch" channel.
    """

    def __init__(
        self,
        *,
        pub_endpoint: str,
        topics: ZmqTopics | None = None,
        run_id: str | None = None,
    ) -> None:
        if topics is None:
            topics = ZmqTopics()

        self._publisher: ZmqPublisher = ZmqPublisher(
                    pub_endpoint=pub_endpoint,
                    topics=topics,
                )
        self._run_id: str | None = run_id

    @property
    def pub_endpoint(self) -> str:
        return self._publisher.pub_endpoint

    @property
    def update_batch(self) -> str:
        return self._publisher.topics.update_batch

    @property
    def run_id(self) -> str | None:
        return self._run_id

    def publish_update(self, batch_payload: JsonObject) -> None:
        # unchanged: caller (publish_progress) now sets top-level "run_id"
        self._publisher.publish_update_batch(batch_payload)

    def publish_progress(
        self,
        *,
        status: Data,
        role_id: str,
        agent_display: str,
        display_content: str,
        turn_id: str,
        source: str,
        session_language: str,
        messenger: str,
        llm_user_message: str,
        llm_system_prompt: str,
        id: str | None = None,
        ts: float | None = None,
        # placeholders required by the inner message schema you already use
        graph: ProcessGraph,
        parsed_edits: list[GraphEdit] | None = None,
        apply_meta: Mapping[str, object] | None,
        follow_up_contexts: FollowUpContexts | None = None,
        last_apply_result: AgentApplyWorkflowEditsResult | None = None,
        run_output: Data | None = None,
        error: Data| None = None,
    ) -> None:
        out = {
            "run_id": self._run_id,
            "status": status,
            "token": {"type": "token", "token": display_content},
            "message": {
                "type": "in_progress",  # do NOT emit the `"message": {"type": "final", ...}`
                "message": {
                    "id": id,
                    "ts": ts if ts is not None else time.time(),
                    "role": agent_display,
                    "content": display_content,
                    "agent": agent_display,
                    "turn_id": turn_id,
                    "source": source,
                    "workflow_response": {
                        "reply": display_content,
                        "result_kind": None,
                    },
                    "parsed_edits": parsed_edits or [],
                    "apply": apply_meta or {},
                    "graph": graph,
                    "run_output": run_output or {},
                    "follow_up_contexts": follow_up_contexts or [],
                    "last_apply_result": last_apply_result or {},
                    "session_language": session_language,
                    "messenger": messenger,
                    "llm_user_message": llm_user_message,
                    "llm_system_prompt": llm_system_prompt,
                },
            },
            "role": {"role_id": role_id, "name": agent_display},
            "error": error,
        }

        self.publish_update(out)
