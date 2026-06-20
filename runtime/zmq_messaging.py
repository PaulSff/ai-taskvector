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


class ZmqPublisher:
    def __init__(
        self,
        *,
        pub_endpoint: str,  # e.g. "tcp://127.0.0.1:5557"
        topics: ZmqTopics = ZmqTopics(),
        linger_ms: int = 0,
        send_timeout_ms: int = 5000,
    ) -> None:
        self.topics = topics
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.PUB)
        sock.linger = linger_ms
        sock.sndtimeo = send_timeout_ms
        sock.connect(pub_endpoint)
        # Let subscribers connect before first publish (PUB/SUB "slow joiner" issue)
        time.sleep(0.2)
        self.sock = sock

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        msg = json.dumps(payload, default=str).encode("utf-8")
        self.sock.send_multipart([topic.encode("utf-8"), msg])

    def publish_job(
        self,
        *,
        run_id: str,
        workflow_path: str,
        initial_inputs: dict[str, Any] | None,
        unit_param_overrides: dict[str, Any] | None,
        format: str | None,
    ) -> None:
        self.publish(
            self.topics.job,
            {
                "run_id": run_id,
                "workflow_path": workflow_path,
                "initial_inputs": initial_inputs,
                "unit_param_overrides": unit_param_overrides,
                "format": format,
                "ts": time.time(),
            },
        )

    def publish_token(self, *, run_id: str, token: str) -> None:
        self.publish(
            self.topics.token,
            {"run_id": run_id, "token": token, "ts": time.time()},
        )

    def publish_result(self, *, run_id: str, outputs: dict[str, Any]) -> None:
        self.publish(
            self.topics.result,
            {"run_id": run_id, "outputs": outputs, "ts": time.time()},
        )

    def publish_error(self, *, run_id: str, error: str) -> None:
        self.publish(
            self.topics.error,
            {"run_id": run_id, "error": error, "ts": time.time()},
        )
