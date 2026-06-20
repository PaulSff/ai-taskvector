# tg_zmq_subscriber.py
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import yaml
import zmq

from messengers_integrations.telegram.telegram_bot_api.telegram_bot_poller import (
    TelegramBotPoller,
)

logger = logging.getLogger("tg_zmq_subscriber")


def setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_conf_yaml(path: str = "conf.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("conf.yaml must be a YAML mapping/object at the root")
    return data


def get_zmq_sub_endpoint(conf: Dict[str, Any]) -> str:
    if conf.get("ZMQ_SUB_ENDPOINT"):
        return str(conf["ZMQ_SUB_ENDPOINT"])
    if conf.get("zmq_sub_endpoint"):
        return str(conf["zmq_sub_endpoint"])
    if isinstance(conf.get("zmq_sub"), dict) and conf["zmq_sub"].get("endpoint"):
        return str(conf["zmq_sub"]["endpoint"])
    raise KeyError("Missing ZMQ_SUB_ENDPOINT in conf.yaml")


def _to_text_tokens(tokens: List[str]) -> str:
    return "".join(tokens) if tokens else ""


def _extract_run_id(payload: Dict[str, Any]) -> Optional[str]:
    rid = payload.get("run_id")
    return str(rid) if rid is not None else None


def _extract_bot_token(payload: Dict[str, Any]) -> Optional[str]:
    # top-level
    for key in ("bot_token", "account"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v

    # nested
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


async def main() -> None:
    setup_logging()
    conf = load_conf_yaml(os.environ.get("CONF_YAML_PATH", "conf.yaml"))
    ZMQ_SUB_ENDPOINT = get_zmq_sub_endpoint(conf)

    logger.info("tg_zmq_subscriber started at: %s", ZMQ_SUB_ENDPOINT)

    poller: Optional[TelegramBotPoller] = None

    chat_ids: Dict[str, str] = {}
    tokens_by_run_id: Dict[str, List[str]] = defaultdict(list)

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.connect(ZMQ_SUB_ENDPOINT)

    # topics
    sock.setsockopt_string(zmq.SUBSCRIBE, "job")
    sock.setsockopt_string(zmq.SUBSCRIBE, "token")
    sock.setsockopt_string(zmq.SUBSCRIBE, "result")
    sock.setsockopt_string(zmq.SUBSCRIBE, "error")

    loop = asyncio.get_running_loop()

    def recv_one() -> Tuple[str, Dict[str, Any]]:
        topic_b, msg_b = sock.recv_multipart()
        return topic_b.decode("utf-8"), json.loads(msg_b.decode("utf-8"))

    try:
        while True:
            topic, payload = await loop.run_in_executor(None, recv_one)
            if not isinstance(payload, dict):
                continue

            run_id = _extract_run_id(payload)
            if not run_id:
                continue

            # Dispatch telegram actions from the job payload
            if topic == "job":
                action, raw = _extract_action_and_raw(payload)
                if not action:
                    continue

                bot_token = _extract_bot_token(payload)
                if not bot_token:
                    logger.warning(
                        "job %s: missing bot_token/account; cannot execute action=%s",
                        run_id,
                        action,
                    )
                    continue

                if poller is None:
                    poller = TelegramBotPoller({"bot_token": bot_token})
                    await poller.start()

                try:
                    if action == "tg_start":
                        # If idempotent, safe; otherwise treat as no-op.
                        await poller.start()
                        continue

                    if action == "tg_stop":
                        await poller.stop(force=True)
                        poller = None
                        continue

                    if action == "get_unread":
                        # If your unit publishes mark_read explicitly, honor it.
                        mark_read = raw.get("mark_read", True)

                        # Ensure poller.get_unread() uses it (it reads from poller.params["mark_read"])
                        poller.params["mark_read"] = bool(mark_read)

                        unread = await poller.get_unread()

                        chat_id = raw.get("chat_id")
                        if chat_id is not None:
                            chat_ids[run_id] = str(chat_id)
                            await poller.send_message(
                                chat_id=str(chat_ids[run_id]),
                                message=f"Unread messages:\n{unread}",
                                wait_for_delivery=bool(
                                    raw.get("wait_for_delivery", True)
                                ),
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
                            continue

                        chat_ids[run_id] = str(chat_id)
                        await poller.send_message(
                            chat_id=str(chat_ids[run_id]),
                            message=str(message),
                            wait_for_delivery=bool(raw.get("wait_for_delivery", True)),
                        )
                        continue

                    if action == "raw":
                        method = raw.get("method")
                        params = raw.get("params")
                        if not isinstance(method, str):
                            logger.warning(
                                "job %s: raw action requires method (str)", run_id
                            )
                            continue
                        await poller.raw(method=method, params=params)
                        continue

                    logger.warning("job %s: unhandled raw.action=%s", run_id, action)

                except Exception:
                    logger.exception(
                        "job %s: failed dispatch action=%s", run_id, action
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

                tokens_by_run_id.pop(run_id, None)
                chat_ids.pop(run_id, None)

            elif topic == "error":
                err = payload.get("error", "Unknown error")
                await poller.send_message(
                    chat_ids[run_id],
                    f"❌ Workflow run {run_id} failed: {err}",
                    wait_for_delivery=True,
                )

                tokens_by_run_id.pop(run_id, None)
                chat_ids.pop(run_id, None)

    except KeyboardInterrupt:
        logger.info("tg_zmq_subscriber received KeyboardInterrupt; shutting down.")
    finally:
        if poller is not None:
            try:
                await poller.stop(force=True)
            except Exception:
                logger.exception("Failed to stop poller cleanly.")
        logger.info("tg_zmq_subscriber stopped.")


if __name__ == "__main__":
    asyncio.run(main())
