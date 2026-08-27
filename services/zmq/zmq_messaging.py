# services/zmq/zmq_messaging.py
from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

import zmq

from core.schemas.primitives import JsonObject
from core.schemas.process_graph import ProcessGraph


@dataclass(frozen=True)
class ZmqTopics:
    job: str = "job"
    token: str = "token"
    result: str = "result"
    error: str = "error"
    update_batch: str = "update_batch"
    action: str = "action"

SocketT = zmq.Socket[bytes]
ContextT = zmq.Context[SocketT]

class MultipartSender(Protocol):
    def send_multipart(
        self,
        msg_parts: Sequence[bytes],
        flags: int = 0,
        copy: bool = True,
        track: bool = False,
    ) -> object:
        ...

class ZmqPublisher:
    topics: ZmqTopics
    sock: MultipartSender
    pub_endpoint: str

    def __init__(
        self,
        *,
        pub_endpoint: str,
        topics: ZmqTopics | None = None,
        linger_ms: int = 0,
        send_timeout_ms: int = 5000,
        slow_joiner_seconds: float = 0.5,
    ) -> None:
        if topics is None:
            topics = ZmqTopics()

        self.topics = topics
        ctx = cast(ContextT, zmq.Context.instance())
        sock = ctx.socket(zmq.PUB)

        sock.linger = linger_ms
        sock.sndtimeo = send_timeout_ms

        _ = sock.bind(pub_endpoint)
        time.sleep(slow_joiner_seconds)

        self.sock = sock
        self.pub_endpoint = pub_endpoint

    def publish(self, topic: str, payload: JsonObject) -> None:
        import logging

        logger = logging.getLogger("ZmqPublisher")
        msg = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        logger.info(
            "ZmqPublisher publish: endpoint=%s topic=%s payload_keys=%s",
            self.pub_endpoint,
            topic,
            list(payload.keys()),
        )

        parts: Sequence[bytes] = (
            topic.encode("utf-8"),
            msg,
        )

        _ = self.sock.send_multipart(parts)

    def publish_job(
        self,
        *,
        run_id: str,
        workflow_path: str | None = None,
        workflow_graph: ProcessGraph | None = None,
        format: str | None = None,
        initial_inputs: JsonObject | None = None,
        unit_param_overrides: JsonObject | None = None,
        response_endpoint: str | None = None,
        update_endpoint: str | None = None,
        execution_timeout_s: float | None = None,
        keep_alive: bool = False,
    ) -> None:
        if (workflow_path is None) == (workflow_graph is None):
            raise ValueError(
                "Provide exactly one of workflow_path or workflow_graph"
            )

        workflow_graph_payload: JsonObject | None = None

        if workflow_graph is not None:
            workflow_graph_payload = workflow_graph.model_dump(mode="json")

        self.publish(
            self.topics.job,
            {
                "run_id": run_id,
                "workflow_path": workflow_path,
                "workflow_graph": workflow_graph_payload,
                "format": format,
                "keep_alive": keep_alive,
                "initial_inputs": initial_inputs,
                "unit_param_overrides": unit_param_overrides,
                "response_endpoint": response_endpoint,
                "update_endpoint": update_endpoint,
                "execution_timeout_s": execution_timeout_s,
                "ts": time.time(),
            },
        )

    def publish_action(
            self,
            *,
            action: str,
            run_id: str,
        ) -> None:
            self.publish(
                self.topics.action,
                {
                    "action": action,
                    "run_id": run_id,
                    "ts": time.time(),
                },
            )

    def publish_token(self, *, run_id: str, token: str) -> None:
        self.publish(
            self.topics.token, {"run_id": run_id, "token": token, "ts": time.time()}
        )

    def publish_result(self, *, run_id: str, outputs: JsonObject) -> None:
        self.publish(
            self.topics.result,
            {"run_id": run_id, "outputs": outputs, "ts": time.time()},
        )

    def publish_error(self, *, run_id: str, error: str) -> None:
        self.publish(
            self.topics.error, {"run_id": run_id, "error": error, "ts": time.time()}
        )

    def publish_update_batch(self, payload: JsonObject) -> None:
        self.publish(self.topics.update_batch, payload)
