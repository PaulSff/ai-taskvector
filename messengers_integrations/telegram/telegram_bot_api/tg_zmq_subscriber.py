# tg_zmq_subscriber.py
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import zmq

from gui.components.settings import get_telegram_bot_token
from messengers_integrations.telegram.telegram_bot_api.telegram_bot_poller import (
    TelegramBotPoller,
)
from runtime import ZmqPublisher, ZmqTopics

from .helpers import (
    default_conf,
    get_zmq_sub_endpoint,
    load_conf_yaml,
)

logger = logging.getLogger("tg_zmq_subscriber")


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
    initial_inputs = payload.get("initial_inputs")
    if not isinstance(initial_inputs, dict):
        return None
    re = initial_inputs.get("response_endpoint")
    return str(re) if isinstance(re, str) and re.strip() else None


def _extract_update_endpoint(payload: Dict[str, Any]) -> Optional[str]:
    initial_inputs = payload.get("initial_inputs")
    if not isinstance(initial_inputs, dict):
        return None
    ue = initial_inputs.get("update_endpoint")
    return str(ue) if isinstance(ue, str) and ue.strip() else None


async def main() -> None:
    import signal

    setup_logging()
    conf = load_conf_yaml(os.environ.get("CONF_YAML_PATH", default_conf))
    ZMQ_SUB_ENDPOINT = get_zmq_sub_endpoint(conf)

    logger.info("tg_zmq_subscriber started at: %s", ZMQ_SUB_ENDPOINT)

    poller: Optional[TelegramBotPoller] = None
    chat_ids: Dict[str, str] = {}
    tokens_by_run_id: Dict[str, List[str]] = defaultdict(list)
    response_endpoint_by_run_id: Dict[str, Optional[str]] = {}

    response_publishers: Dict[str, ZmqPublisher] = {}

    update_publishers: Dict[str, ZmqPublisher] = {}
    update_endpoints_by_run_id: Dict[str, Optional[str]] = {}

    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _request_stop)
        except NotImplementedError:
            # Fallback if signal handlers can't be installed
            pass

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.connect(ZMQ_SUB_ENDPOINT)

    # topics
    sock.setsockopt_string(zmq.SUBSCRIBE, "job")
    sock.setsockopt_string(zmq.SUBSCRIBE, "token")
    sock.setsockopt_string(zmq.SUBSCRIBE, "result")
    sock.setsockopt_string(zmq.SUBSCRIBE, "error")

    # Don't hang forever on Ctrl+C; allow loop to re-check stop_event.
    sock.RCVTIMEO = 1000  # ms

    def recv_one() -> Tuple[str, Dict[str, Any]]:
        try:
            parts = sock.recv_multipart(flags=0)
        except zmq.error.Again:
            return "", {}

        if not parts:
            return "", {}

        if len(parts) == 1:
            topic_b = b""
            msg_b = parts[0]
        else:
            topic_b = parts[0]
            msg_b = parts[1]

        topic_s = topic_b.decode("utf-8", errors="replace") if topic_b else ""

        logger.info(
            "tg_zmq_subscriber recv: endpoint=%s topic=%s frames=%d msg_bytes=%d",
            ZMQ_SUB_ENDPOINT,
            topic_s,
            len(parts),
            len(msg_b),
        )

        try:
            return topic_s, json.loads(msg_b.decode("utf-8"))
        except Exception:
            logger.exception(
                "tg_zmq_subscriber JSON parse failed: topic=%s raw_sample=%r",
                topic_s,
                msg_b[:200],
            )
            return topic_s, {}

    def _publish_response(
        *,
        response_endpoint: Optional[str],
        run_id: str,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        if not response_endpoint:
            return
        pub = response_publishers.get(response_endpoint)
        if pub is None:
            pub = ZmqPublisher(pub_endpoint=response_endpoint, topics=ZmqTopics())
            response_publishers[response_endpoint] = pub
        pub.publish(topic, {"run_id": run_id, "response": payload})

    def _publish_update_batch(
        *, update_endpoint: Optional[str], payload: Dict[str, Any]
    ) -> None:
        if not update_endpoint:
            return
        pub = update_publishers.get(update_endpoint)
        if pub is None:
            pub = ZmqPublisher(pub_endpoint=update_endpoint, topics=ZmqTopics())
            update_publishers[update_endpoint] = pub
        pub.publish(ZmqTopics().update_batch, payload)

    try:
        while not stop_event.is_set():
            topic, payload = await loop.run_in_executor(None, recv_one)
            if stop_event.is_set():
                break

            if topic == "" and payload == {}:
                continue

            if topic == "job":
                try:
                    action_dbg = None
                    initial_inputs_dbg = (
                        payload.get("initial_inputs")
                        if isinstance(payload, dict)
                        else None
                    )
                    if isinstance(initial_inputs_dbg, dict) and isinstance(
                        initial_inputs_dbg.get("raw"), dict
                    ):
                        action_dbg = initial_inputs_dbg["raw"].get("action")
                    logger.info(
                        "tg_zmq_subscriber job received: run_id=%s workflow_path=%s action=%s keys=%s",
                        payload.get("run_id"),
                        payload.get("workflow_path"),
                        action_dbg,
                        list(payload.get("initial_inputs", {}).keys())
                        if isinstance(payload.get("initial_inputs"), dict)
                        else None,
                    )
                    logger.info("tg_zmq_subscriber job payload: %s", payload)
                except Exception:
                    logger.exception("tg_zmq_subscriber job logging failed")

            if not isinstance(payload, dict):
                continue

            run_id = _extract_run_id(payload)
            if not run_id:
                continue

            # Track endpoints from the job payload for later result/error messages
            if topic == "job":
                response_endpoint_by_run_id[run_id] = _extract_response_endpoint(
                    payload
                )
                update_endpoints_by_run_id[run_id] = _extract_update_endpoint(payload)

            if topic == "job":
                action, raw = _extract_action_and_raw(payload)
                if not action:
                    continue

                bot_token = _extract_bot_token(payload)
                if not bot_token:
                    bot_token = get_telegram_bot_token()
                    if not isinstance(bot_token, str) or not bot_token.strip():
                        logger.warning(
                            "job %s: missing bot_token/account; cannot execute action=%s",
                            run_id,
                            action,
                        )
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
                        continue

                if poller is None:
                    poller = TelegramBotPoller({"bot_token": bot_token})
                    await poller.start()

                try:
                    if action == "tg_start":
                        await poller.start()
                        continue

                    if action == "tg_stop":
                        await poller.stop(force=True)
                        poller = None
                        continue

                    if action == "get_unread":
                        mark_read = raw.get("mark_read", True)
                        poller.params["mark_read"] = bool(mark_read)

                        unread = await poller.get_unread()

                        result_payload: Dict[str, Any] = {"unread": unread}

                        chat_id = raw.get("chat_id")
                        if chat_id is not None:
                            chat_ids[run_id] = str(chat_id)
                            await poller.send_message(
                                chat_id=chat_ids[run_id],
                                message=f"Unread messages:\n{unread}",
                                wait_for_delivery=bool(
                                    raw.get("wait_for_delivery", True)
                                ),
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
                        continue

                    if action == "send_message":
                        chat_id = raw.get("chat_id")
                        message = raw.get("message")
                        if chat_id is None or message is None:
                            logger.warning(
                                "job %s: send_message requires chat_id and message",
                                run_id,
                            )
                            _publish_response(
                                response_endpoint=response_endpoint_by_run_id.get(
                                    run_id
                                ),
                                run_id=run_id,
                                topic=ZmqTopics().error,
                                payload={
                                    "status": "error",
                                    "action": action,
                                    "error": "send_message requires chat_id and message",
                                },
                            )
                            continue

                        chat_ids[run_id] = str(chat_id)
                        await poller.send_message(
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
                            },
                        )
                        continue

                    if action == "raw":
                        method = raw.get("method")
                        params = raw.get("params")
                        if not isinstance(method, str):
                            logger.warning(
                                "job %s: raw action requires method (str)", run_id
                            )
                            _publish_response(
                                response_endpoint=response_endpoint_by_run_id.get(
                                    run_id
                                ),
                                run_id=run_id,
                                topic=ZmqTopics().error,
                                payload={
                                    "status": "error",
                                    "action": action,
                                    "error": "raw action requires method (str)",
                                },
                            )
                            continue

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
                        continue

                    logger.warning("job %s: unhandled raw.action=%s", run_id, action)
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
                    logger.exception(
                        "job %s: failed dispatch action=%s", run_id, action
                    )
                    _publish_response(
                        response_endpoint=response_endpoint_by_run_id.get(run_id),
                        run_id=run_id,
                        topic=ZmqTopics().error,
                        payload={
                            "status": "error",
                            "action": action,
                            "error": str(e),
                        },
                    )
                continue

            # For result/error, send final message using run_id -> chat_id mapping
            if run_id not in chat_ids or poller is None:
                continue

            if topic == "token":
                tok = payload.get("token")
                if isinstance(tok, str):
                    tokens_by_run_id[run_id].append(tok)

            elif topic == "result":
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
                    payload={
                        "status": "ok",
                        "outputs": outputs,
                        "final_text": final_text,
                    },
                )

                tokens_by_run_id.pop(run_id, None)
                chat_ids.pop(run_id, None)
                response_endpoint_by_run_id.pop(run_id, None)
                update_endpoints_by_run_id.pop(run_id, None)

            elif topic == "error":
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
                update_endpoints_by_run_id.pop(run_id, None)

    finally:
        if poller is not None:
            try:
                await poller.stop(force=True)
            except Exception:
                logger.exception("Failed to stop poller cleanly.")
        sock.close(linger=0)
        logger.info("tg_zmq_subscriber stopped.")


if __name__ == "__main__":
    asyncio.run(main())
