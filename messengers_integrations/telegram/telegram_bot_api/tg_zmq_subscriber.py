# tg_zmq_subscriber.py
from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from gui.components.settings import get_telegram_bot_token
from messengers_integrations.telegram.telegram_bot_api.helpers import (
    default_conf,
    get_zmq_sub_endpoint,
    load_conf_yaml,
)
from messengers_integrations.telegram.telegram_bot_api.telegram_bot_poller import (
    TelegramBotPoller,
)
from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

logger = logging.getLogger("tg_zmq_subscriber")


class TgZmqSubscriberService:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.get_running_loop().create_task(main())

    async def stop(self) -> None:
        t = self._task
        self._task = None
        if t and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


def setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _to_text_tokens(tokens: List[str]) -> str:
    return "".join(tokens) if tokens else ""


def _extract_run_id(payload: Dict[str, Any]) -> Optional[str]:
    rid = payload.get("run_id")
    return str(rid) if rid is not None else None


def _extract_bot_token(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("bot_token", "account"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v

    for container_key in ("unit_params", "params"):
        container = payload.get(container_key)
        if isinstance(container, dict):
            for key in ("bot_token", "account"):
                v = container.get(key)
                if isinstance(v, str) and v.strip():
                    return v

    return None


def _extract_action_and_raw(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], Dict[str, Any]]:
    initial_inputs = payload.get("initial_inputs")
    if not isinstance(initial_inputs, dict):
        return None, {}

    raw = initial_inputs.get("raw")
    if not isinstance(raw, dict):
        return None, {}

    action = raw.get("action")
    return (str(action) if action is not None else None), raw


def _extract_response_endpoint(payload: Dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    # 1) where your logs suggest it is: top-level
    re = payload.get("response_endpoint")
    if isinstance(re, str) and re.strip():
        return re

    # 2) fallback: nested under initial_inputs
    initial_inputs = payload.get("initial_inputs")
    if isinstance(initial_inputs, dict):
        re = initial_inputs.get("response_endpoint")
        if isinstance(re, str) and re.strip():
            return re

    return None


def _extract_update_endpoint(payload: Dict[str, Any]) -> Optional[str]:
    initial_inputs = payload.get("initial_inputs")
    if not isinstance(initial_inputs, dict):
        return None
    ue = initial_inputs.get("update_endpoint")
    return str(ue) if isinstance(ue, str) and ue.strip() else None


async def main() -> None:
    setup_logging()
    conf = load_conf_yaml(os.environ.get("CONF_YAML_PATH", default_conf))
    ZMQ_SUB_ENDPOINT = get_zmq_sub_endpoint(conf)

    logger.info("TgZmqSubscriberService started at: %s", ZMQ_SUB_ENDPOINT)

    poller: Optional[TelegramBotPoller] = None

    chat_ids: Dict[str, str] = {}
    tokens_by_run_id: Dict[str, List[str]] = defaultdict(list)
    response_endpoint_by_run_id: Dict[str, Optional[str]] = {}
    update_endpoint_by_run_id: Dict[str, Optional[str]] = {}

    response_publishers: Dict[str, ZmqPublisher] = {}
    update_publishers: Dict[str, ZmqPublisher] = {}

    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _request_stop)
        except NotImplementedError:
            pass

    sub = ZmqSubscriber(
        config=ZmqSubscriptionConfig(
            sub_endpoint=ZMQ_SUB_ENDPOINT,
            topics=["job", "token", "result", "error"],
            rcvtimeo_ms=1000,
        )
    )

    def _get_response_publisher(endpoint: Optional[str]) -> Optional[ZmqPublisher]:
        if not endpoint:
            return None
        pub = response_publishers.get(endpoint)
        if pub is None:
            pub = ZmqPublisher(pub_endpoint=endpoint, topics=ZmqTopics())
            response_publishers[endpoint] = pub
        return pub

    def _get_update_publisher(endpoint: Optional[str]) -> Optional[ZmqPublisher]:
        if not endpoint:
            return None
        pub = update_publishers.get(endpoint)
        if pub is None:
            pub = ZmqPublisher(pub_endpoint=endpoint, topics=ZmqTopics())
            update_publishers[endpoint] = pub
        return pub

    def _publish_response(
        *,
        response_endpoint: Optional[str],
        run_id: str,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        # log "response sent"
        logger.info(
            "responses: topic=%s run_id=%s endpoint=%s payload_status=%s",
            topic,
            run_id,
            response_endpoint,
            payload.get("status"),
        )

        pub = _get_response_publisher(response_endpoint)
        if pub is None:
            logger.warning(
                "responses: skip (no response publisher) topic=%s run_id=%s endpoint=%s",
                topic,
                run_id,
                response_endpoint,
            )
            return
        pub.publish(topic, {"run_id": run_id, "response": payload})

    async def _ensure_poller_started(bot_token: str) -> TelegramBotPoller:
        nonlocal poller
        if poller is None:
            poller = TelegramBotPoller({"bot_token": bot_token})
            await poller.start()
        return poller

    async def _handle(topic: str, payload: Dict[str, Any]) -> None:
        nonlocal poller

        if not isinstance(payload, dict):
            return

        run_id = _extract_run_id(payload)

        # log "job received" (and other message types)
        logger.info(
            "jobs received: topic=%s run_id=%s keys=%s",
            topic,
            run_id,
            list(payload.keys()),
        )

        if not run_id:
            return

        if topic == "job":
            response_endpoint_by_run_id[run_id] = _extract_response_endpoint(payload)
            update_endpoint_by_run_id[run_id] = _extract_update_endpoint(payload)

            action, raw = _extract_action_and_raw(payload)
            if not action:
                return

            bot_token = _extract_bot_token(payload)
            if not bot_token:
                bot_token = get_telegram_bot_token()
                if not isinstance(bot_token, str) or not bot_token.strip():
                    _publish_response(
                        response_endpoint=response_endpoint_by_run_id.get(run_id),
                        run_id=run_id,
                        topic=ZmqTopics().error,
                        payload={
                            "status": "error",
                            "action": action,
                            "error": "Missing bot_token/account",
                        },
                    )
                    return

            if poller is None:
                poller = TelegramBotPoller({"bot_token": bot_token})
                await poller.start()

            try:
                if action == "tg_start":
                    await poller.start()
                    return

                if action == "tg_stop":
                    await poller.stop(force=True)
                    poller = None
                    return

                if action == "get_unread":
                    poller = await _ensure_poller_started(bot_token)
                    poller.params["mark_read"] = bool(raw.get("mark_read", True))
                    unread = await poller.get_unread()

                    result_payload: Dict[str, Any] = {"unread": unread}

                    chat_id = raw.get("chat_id")
                    if chat_id is not None:
                        chat_ids[run_id] = str(chat_id)
                        await poller.send_message(
                            chat_id=chat_ids[run_id],
                            message=f"Unread messages:\n{unread}",
                            wait_for_delivery=bool(raw.get("wait_for_delivery", True)),
                        )
                        result_payload["sent_to_chat_id"] = chat_ids[run_id]

                    _publish_response(
                        response_endpoint=response_endpoint_by_run_id.get(run_id),
                        run_id=run_id,
                        topic=ZmqTopics().result,
                        payload={
                            "status": "ok",
                            "action": action,
                            **result_payload,
                        },
                    )
                    return

                if action == "send_message":
                    chat_id = raw.get("chat_id")
                    message = raw.get("message")
                    if chat_id is None or message is None:
                        _publish_response(
                            response_endpoint=response_endpoint_by_run_id.get(run_id),
                            run_id=run_id,
                            topic=ZmqTopics().error,
                            payload={
                                "status": "error",
                                "action": action,
                                "error": "send_message requires chat_id and message",
                            },
                        )
                        return

                    chat_ids[run_id] = str(chat_id)

                    poller = await _ensure_poller_started(
                        bot_token
                    )  # <-- this calls await poller.start()

                    poller_resp = await poller.send_message(
                        chat_id=chat_ids[run_id],
                        message=str(message),
                        wait_for_delivery=bool(raw.get("wait_for_delivery", True)),
                    )

                    _publish_response(
                        response_endpoint=response_endpoint_by_run_id.get(run_id),
                        run_id=run_id,
                        topic=ZmqTopics().result,
                        payload={
                            "status": "ok",
                            "action": action,
                            "sent_to_chat_id": chat_ids[run_id],
                            "message": str(message),
                            "poller_response": poller_resp,
                        },
                    )
                    return

                if action == "raw":
                    method = raw.get("method")
                    params = raw.get("params")
                    if not isinstance(method, str):
                        _publish_response(
                            response_endpoint=response_endpoint_by_run_id.get(run_id),
                            run_id=run_id,
                            topic=ZmqTopics().error,
                            payload={
                                "status": "error",
                                "action": action,
                                "error": "raw action requires method (str)",
                            },
                        )
                        return

                    raw_result = await poller.raw(method=method, params=params)

                    _publish_response(
                        response_endpoint=response_endpoint_by_run_id.get(run_id),
                        run_id=run_id,
                        topic=ZmqTopics().result,
                        payload={
                            "status": "ok",
                            "action": action,
                            "method": method,
                            "params": params,
                            "raw_result": raw_result,
                        },
                    )
                    return

                _publish_response(
                    response_endpoint=response_endpoint_by_run_id.get(run_id),
                    run_id=run_id,
                    topic=ZmqTopics().error,
                    payload={
                        "status": "error",
                        "action": action,
                        "error": f"Unhandled action: {action}",
                    },
                )
            except Exception as e:
                logger.exception("job %s: failed dispatch action=%s", run_id, action)
                _publish_response(
                    response_endpoint=response_endpoint_by_run_id.get(run_id),
                    run_id=run_id,
                    topic=ZmqTopics().error,
                    payload={"status": "error", "action": action, "error": str(e)},
                )
            return

        # token/result/error messages (final delivery to telegram)
        if run_id not in chat_ids or poller is None:
            return

        if topic == "token":
            tok = payload.get("token")
            if isinstance(tok, str):
                tokens_by_run_id[run_id].append(tok)
            return

        if topic == "result":
            outputs = payload.get("outputs", {})
            token_text = _to_text_tokens(tokens_by_run_id.get(run_id, []))

            streaming_part = ""
            if token_text:
                streaming_part = "Streaming output:\n" + token_text

            final_text = (
                f"Workflow run {run_id} completed.\n"
                f"{streaming_part}\n"
                f"Outputs keys: {list(outputs.keys()) if isinstance(outputs, dict) else type(outputs).__name__}"
            )

            await poller.send_message(
                chat_ids[run_id], final_text, wait_for_delivery=True
            )

            _publish_response(
                response_endpoint=response_endpoint_by_run_id.get(run_id),
                run_id=run_id,
                topic=ZmqTopics().result,
                payload={"status": "ok", "outputs": outputs, "final_text": final_text},
            )

            tokens_by_run_id.pop(run_id, None)
            chat_ids.pop(run_id, None)
            response_endpoint_by_run_id.pop(run_id, None)
            update_endpoint_by_run_id.pop(run_id, None)
            return

        if topic == "error":
            err = payload.get("error", "Unknown error")
            await poller.send_message(
                chat_ids[run_id],
                f"❌ Workflow run {run_id} failed: {err}",
                wait_for_delivery=True,
            )

            _publish_response(
                response_endpoint=response_endpoint_by_run_id.get(run_id),
                run_id=run_id,
                topic=ZmqTopics().error,
                payload={
                    "status": "error",
                    "error": err,
                    "final_text": f"❌ Workflow run {run_id} failed: {err}",
                },
            )

            tokens_by_run_id.pop(run_id, None)
            chat_ids.pop(run_id, None)
            response_endpoint_by_run_id.pop(run_id, None)
            update_endpoint_by_run_id.pop(run_id, None)
            return

    # register handlers
    sub.on("job", _handle)
    sub.on("token", _handle)
    sub.on("result", _handle)
    sub.on("error", _handle)

    await sub.start()

    try:
        while not stop_event.is_set():
            await asyncio.sleep(0.2)
    finally:
        await sub.stop()
        if poller is not None:
            try:
                await poller.stop(force=True)
            except Exception:
                logger.exception("Failed to stop poller cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
