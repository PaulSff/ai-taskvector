"""
Start + listen:
    python tg_cli.py --params-json '{"bot_token":"YOUR_BOT_TOKEN"}' listen
Get unread:
    python tg_cli.py --params-json '{"bot_token":"YOUR_BOT_TOKEN"}' get_unread
Send:
    python tg_cli.py --params-json '{"bot_token":"YOUR_BOT_TOKEN"}' send_message 123456 "hello"

"""

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, Optional

from messengers_integrations.telegram.telegram_bot_api.telegram_bot_poller import (
    TelegramBotPoller,
)


def parse_json_maybe(s: Optional[str]) -> Optional[Dict[str, Any]]:
    if s is None:
        return None
    return json.loads(s)


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def print_event(ev: Dict[str, Any]) -> None:
    t = ev.get("type")
    status = ev.get("status")
    error = ev.get("error")

    if t == "update_batch":
        print(f"\n[update_batch] status={status!r} error={bool(error)}")
        upd = ev.get("update")
        if upd is not None:
            print(dump(upd))
        else:
            print("(no update)")
        return

    print(f"\n[{t}]")
    print(dump(ev))


async def main_async(args: argparse.Namespace) -> int:
    params: Dict[str, Any] = {}
    if args.params_json:
        params.update(parse_json_maybe(args.params_json) or {})

    poller = TelegramBotPoller(params)

    start_res = await poller.start()
    print(dump(start_res))

    async def printer() -> None:
        async for ev in poller.subscribe():
            print_event(ev)

    listen_task: Optional[asyncio.Task] = None
    if args.command == "listen":
        listen_task = asyncio.create_task(printer())

    try:
        if args.command == "get_unread":
            res = await poller.get_unread()
            print("\n[get_unread] result:")
            print(dump(res))
            return 0

        if args.command == "send_message":
            msg: Any = args.message
            if args.message_json:
                msg = json.loads(args.message)

            res = await poller.send_message(
                args.chat_id,
                msg,
                wait_for_delivery=not args.no_wait_for_delivery,
            )
            print("\n[send_message] result:")
            print(dump(res))
            return 0

        if args.command == "raw":
            params2 = parse_json_maybe(args.params)
            res = await poller.raw(args.method, params=params2)
            print("\n[raw] result:")
            print(dump(res))
            return 0

        if args.command == "listen":
            while True:
                await asyncio.sleep(3600)

    finally:
        if listen_task:
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass

        if not args.keep_running:
            stop_res = await poller.stop(force=args.force_stop)
            print("\n[stop] result:")
            print(dump(stop_res))

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CLI for TelegramBotPoller")
    p.add_argument(
        "--params-json",
        help="JSON string with bot_token/account and optional timeouts. Example: "
        '\'{"bot_token":"..."}\'',
        required=True,
    )
    p.add_argument("--force-stop", action="store_true", help="Force stop on exit")
    p.add_argument(
        "--keep-running",
        action="store_true",
        help="Do not automatically stop poller when the command exits "
        "(e.g., after get_unread/raw/send_message).",
    )

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("listen", help="Listen for update_batch events")

    sub.add_parser("get_unread", help="Call get_unread()")

    s_send = sub.add_parser("send_message", help="Send a message")
    s_send.add_argument("chat_id")
    s_send.add_argument("message", help="Message text")
    s_send.add_argument("--message-json", action="store_true")
    s_send.add_argument("--no-wait-for-delivery", action="store_true")

    s_raw = sub.add_parser("raw", help="Call raw(method, params)")
    s_raw.add_argument("method")
    s_raw.add_argument("--params", help="JSON params object for the raw call")

    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        rc = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
