from __future__ import annotations

import asyncio
import uuid
from typing import Any, Awaitable, Callable, Optional

from runtime.zmq_messaging import ZmqPublisher, ZmqTopics
from runtime.zmq_subscriber import ZmqSubscriber, ZmqSubscriptionConfig

ResponseHandler = Callable[[dict[str, Any]], Awaitable[None]]
ErrorHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class WorkflowServerClient:
    """
    Transport-only component for running a workflow via a workflow server:
    - PUB job to WORKFLOW_SERVER_ENDPOINT
    - SUB to RAG_INDEX_RESPONSE_ENDPOINT topics.result/topics.error
    - return the workflow output under `result` key (preserves caller expectations)
    - shut down gracefully
    """

    def __init__(
        self,
        *,
        pub_endpoint: str,  # WORKFLOW_SERVER_ENDPOINT, e.g. "tcp://127.0.0.1:6666"
        sub_endpoint: str,  # RAG_INDEX_RESPONSE_ENDPOINT, e.g. "tcp://127.0.0.1:6668"
        response_timeout_s: float = 120.0,
        topics: ZmqTopics = ZmqTopics(),
        on_response: Optional[ResponseHandler] = None,
        on_error: Optional[ErrorHandler] = None,
    ) -> None:
        self._topics = topics
        self._pub = ZmqPublisher(pub_endpoint=pub_endpoint, topics=topics)
        self._sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=sub_endpoint,
                topics=[topics.result, topics.error],
                accept_topics=[topics.result, topics.error],
            )
        )
        self._sub_endpoint = sub_endpoint
        self._response_timeout_s = response_timeout_s
        self._on_response = on_response
        self._on_error = on_error

        self._run_id: Optional[str] = None
        self._result_future: Optional[asyncio.Future[dict[str, Any]]] = None

        async def _handle_result(topic: str, payload: dict[str, Any]) -> None:
            await self._handle_result_payload(payload)

        async def _handle_error(topic: str, payload: dict[str, Any]) -> None:
            await self._handle_error_payload(payload)

        self._sub.on(self._topics.result, _handle_result)
        self._sub.on(self._topics.error, _handle_error)

    async def _handle_result_payload(self, payload: dict[str, Any]) -> None:
        # Expected: {"run_id": "...", "result": {...}, "ts": ...} (per your note)
        if self._run_id is not None and payload.get("run_id") != self._run_id:
            return

        if self._result_future is None or self._result_future.done():
            return

        result = payload.get("result")
        if not isinstance(payload, dict):
            self._result_future.set_result(
                {"error": "Malformed result payload", "payload": payload}
            )
            return

        # Preserve "exactly like it currently does":
        # return the same shape as run_workflow() caller expects.
        # In current code: outputs = (outputs or {}).get("chroma", {})
        # so we return {"result": <workflow output dict>} and let caller treat it like `outputs`.
        if isinstance(result, dict):
            self._result_future.set_result({"result": result})
        else:
            self._result_future.set_result(
                {"error": "Missing/invalid `result` key", "payload": payload}
            )

        if self._on_response is not None:
            await self._on_response({"result": result, "payload": payload})

    async def _handle_error_payload(self, payload: dict[str, Any]) -> None:
        # Expected: {"run_id": "...", "error": "...", "ts": ...}
        if self._run_id is not None and payload.get("run_id") != self._run_id:
            return

        if self._result_future is None or self._result_future.done():
            return

        err = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(err, str):
            err = "Unknown error"

        self._result_future.set_result({"error": err, "payload": payload})

        if self._on_error is not None:
            await self._on_error(err, payload)

    async def run(
        self,
        *,
        workflow_path: str,
        unit_param_overrides: dict[str, Any],
        initial_inputs: Optional[dict[str, Any]] = None,
        format: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Returns:
          - on success: {"result": <raw workflow outputs dict>}
          - on error:   {"error": "<message>", "payload": <raw error payload>}
        """
        self._run_id = str(uuid.uuid4())
        self._result_future = asyncio.get_running_loop().create_future()

        await self._sub.start()
        try:
            self._pub.publish_job(
                run_id=self._run_id,
                workflow_path=workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format=format,
                # crucial: send responses back to our subscriber endpoint
                response_endpoint=self._sub_endpoint,
                update_endpoint=None,
            )

            result = await asyncio.wait_for(
                self._result_future, timeout=self._response_timeout_s
            )
            return result
        finally:
            await self._sub.stop()

    async def close(self) -> None:
        await self._sub.stop()
