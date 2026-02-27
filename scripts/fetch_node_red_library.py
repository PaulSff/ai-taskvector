#!/usr/bin/env python3
"""
Fetch the full Node-RED Flow Library (nodes, flows, collections) from
https://flows.nodered.org/things?format=json&type=<type>&page=<n>

Usage:
  python scripts/fetch_node_red_library.py [--out-dir mydata] [--delay 1.2] [--per-page 15]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

BASE = "https://flows.nodered.org/things"
# Control chars that break JSON when inside a string (except \t \n \r)
_JSON_UNSAFE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Keys to strip from Node-RED flow nodes (credentials, etc.) — match refine script
_FLOW_STRIP_KEYS = frozenset(
    {"credentials", "privateKey", "certificate", "token", "password", "secret", "key", "apiKey"}
)
# Output format: only these keys per flow entry (match refine script)
FLOW_ESSENTIAL_KEYS = ("_id", "url", "created_at", "updated_at", "flow", "readme", "summary", "gitOwners")


def _sanitize_string(s: str) -> str:
    """Replace invalid UTF-8 and JSON-unsafe control characters so json.dump never fails."""
    if not isinstance(s, str):
        return s
    s = s.encode("utf-8", errors="replace").decode("utf-8")
    return _JSON_UNSAFE_RE.sub("\uFFFD", s)


def sanitize_for_json(obj: Any) -> Any:
    """Recursively sanitize so the result is always JSON-serializable and valid."""
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return _sanitize_string(obj)
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj


def _strip_sensitive(obj: Any) -> Any:
    """Recursively remove credential-like keys from a Node-RED node object."""
    if isinstance(obj, dict):
        return {k: _strip_sensitive(v) for k, v in obj.items() if k not in _FLOW_STRIP_KEYS}
    if isinstance(obj, list):
        return [_strip_sensitive(v) for v in obj]
    return obj


def _flow_string_to_list(flow_str: str) -> list[Any] | str:
    """
    Parse flow JSON string to list of nodes, strip credentials. Returns list or "[invalid]".
    Output is real JSON array (no \"...\" in file).
    """
    if not flow_str or not flow_str.strip():
        return []
    raw = _JSON_UNSAFE_RE.sub("\uFFFD", flow_str)
    try:
        flow_data = json.loads(raw)
    except json.JSONDecodeError:
        return "[invalid]"
    if not isinstance(flow_data, list):
        return "[invalid]"
    return [_strip_sensitive(n) for n in flow_data]


def _to_string(val: Any) -> str:
    """Normalize readme/summary to string: keep str, convert list/dict to JSON string."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, dict)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def _normalize_flow_item(item: dict[str, Any]) -> dict[str, Any]:
    """Reduce to essential keys and parse flow to list (refined output format). readme/summary can be string or parsed JSON."""
    out = {k: item[k] for k in FLOW_ESSENTIAL_KEYS if k in item}
    if "flow" in out and out["flow"]:
        raw = out["flow"] if isinstance(out["flow"], str) else ""
        out["flow"] = _flow_string_to_list(raw)
    elif "flow" in out:
        out["flow"] = []
    if "readme" in out:
        out["readme"] = _to_string(out["readme"])
    if "summary" in out:
        out["summary"] = _to_string(out["summary"])
    return out


DEFAULT_DELAY = 1.2  # seconds between requests (rate-limit friendly)
DEFAULT_PER_PAGE = 15  # site default
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds


def fetch_page(
    type: str,
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
    timeout: int = REQUEST_TIMEOUT,
) -> dict:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                BASE,
                params={"format": "json", "type": type, "page": page, "per_page": per_page},
                timeout=timeout,
                headers={"User-Agent": "Node-RED-Library-Fetch/1.0"},
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF * (attempt + 1)
                print(f"    Retry in {wait}s after {e!r}")
                time.sleep(wait)
            else:
                raise


def fetch_all(
    type: str,
    out_path: Path,
    delay: float = DEFAULT_DELAY,
    per_page: int = DEFAULT_PER_PAGE,
    save_every: int = 1,
) -> int:
    all_items = []
    page = 1
    total_pages = None

    while True:
        data = fetch_page(type, page=page, per_page=per_page)
        things = data.get("data") or []
        for t in things:
            item = sanitize_for_json(t)
            if type == "flow":
                item = _normalize_flow_item(item)
            all_items.append(item)

        meta = data.get("meta") or {}
        results = meta.get("results") or {}
        pages = meta.get("pages") or {}
        count = results.get("count", 0)
        total_pages = pages.get("total", 1)

        print(f"  {type}: page {page}/{total_pages} ({len(things)} items, total so far: {len(all_items)}/{count})")

        if save_every and (page % save_every == 0 or page >= total_pages or not things):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(all_items, f, ensure_ascii=False, indent=2)

        if page >= total_pages or not things:
            break
        page += 1
        time.sleep(delay)

    print(f"  Saved {len(all_items)} {type}s to {out_path}")
    return len(all_items)


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch Node-RED Flow Library (nodes, flows, collections)")
    p.add_argument("--out-dir", type=Path, default=Path("mydata"), help="Output directory")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between requests")
    p.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE, help="Items per page (max ~15 respected by site)")
    p.add_argument(
        "--only",
        choices=["node", "flow", "collection"],
        action="append",
        default=None,
        help="Fetch only these types (default: all). Can be repeated.",
    )
    args = p.parse_args()

    types = args.only or ["node", "flow", "collection"]
    out_dir = args.out_dir.resolve()
    print(f"Output directory: {out_dir}\n")

    for lib_type in types:
        out_path = out_dir / f"node-red-library-{lib_type}s.json"
        fetch_all(lib_type, out_path, delay=args.delay, per_page=args.per_page, save_every=1)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
