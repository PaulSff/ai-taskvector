# runtime/zmq_messaging.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import zmq


@dataclass(frozen=True)
class ZmqTopics:
    job: str = "job"
    token: str = "token"
    result: str = "result"
    error: str = "error"
    update_batch: str = "update_batch"


class ZmqPublisher:
    def __init__(
        self,
        *,
        pub_endpoint: str,
        topics: ZmqTopics = ZmqTopics(),
        linger_ms: int = 0,
        send_timeout_ms: int = 5000,
        slow_joiner_seconds: float = 0.5,
    ) -> None:
        self.topics = topics
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.PUB)

        sock.linger = linger_ms
        sock.sndtimeo = send_timeout_ms

        sock.bind(pub_endpoint)
        time.sleep(slow_joiner_seconds)

        self.sock = sock
        self.pub_endpoint = pub_endpoint

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        import logging

        logger = logging.getLogger("ZmqPublisher")
        msg = json.dumps(payload, default=str).encode("utf-8")

        logger.info(
            "ZmqPublisher publish: endpoint=%s topic=%s payload_keys=%s",
            self.pub_endpoint,
            topic,
            list(payload.keys())
            if isinstance(payload, dict)
            else type(payload).__name__,
        )

        self.sock.send_multipart([topic.encode("utf-8"), msg])

    def publish_job(
        self,
        *,
        run_id: str,
        workflow_path: str | None = None,
        workflow_graph: dict[str, Any] | None = None,
        format: str | None = None,
        initial_inputs: dict[str, Any] | None,
        unit_param_overrides: dict[str, Any] | None,
        response_endpoint: str | None = None,
        update_endpoint: str | None = None,
    ) -> None:
        if (workflow_path is None) == (workflow_graph is None):
            raise ValueError("Provide exactly one of workflow_path or workflow_graph")

        self.publish(
            self.topics.job,
            {
                "run_id": run_id,
                "workflow_path": workflow_path,
                "workflow_graph": workflow_graph,
                "format": format,
                "initial_inputs": initial_inputs,
                "unit_param_overrides": unit_param_overrides,
                "response_endpoint": response_endpoint,
                "update_endpoint": update_endpoint,
                "ts": time.time(),
            },
        )

    def publish_token(self, *, run_id: str, token: str) -> None:
        self.publish(
            self.topics.token, {"run_id": run_id, "token": token, "ts": time.time()}
        )

    def publish_result(self, *, run_id: str, outputs: dict[str, Any]) -> None:
        self.publish(
            self.topics.result,
            {"run_id": run_id, "outputs": outputs, "ts": time.time()},
        )

    def publish_error(self, *, run_id: str, error: str) -> None:
        self.publish(
            self.topics.error, {"run_id": run_id, "error": error, "ts": time.time()}
        )

    def publish_update_batch(self, payload: dict[str, Any]) -> None:
        self.publish(self.topics.update_batch, payload)
