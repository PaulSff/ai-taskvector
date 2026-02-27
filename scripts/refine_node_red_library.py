#!/usr/bin/env python3
"""
Refine downloaded Node-RED Flow Library data:
- Repair invalid JSON (e.g. flows with embedded control chars)
- Optionally trim heavy fields (readme, flow) for smaller summary files
- Normalize and dedupe by id

Usage:
  python scripts/refine_node_red_library.py [--data-dir mydata] [--trim] [--summary]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# Same as in fetch_node_red_library.py: control chars that break JSON
_JSON_UNSAFE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Keys to strip from Node-RED flow nodes (credentials, keys, tokens, etc.)
_FLOW_STRIP_KEYS = frozenset(
    {"credentials", "privateKey", "certificate", "token", "password", "secret", "key", "apiKey"}
)

# Essential keys to keep for each flow library entry (all other fields removed)
FLOW_ESSENTIAL_KEYS = ("_id", "url", "created_at", "updated_at", "flow", "readme", "summary", "gitOwners")


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


def repair_json_string(raw: str) -> str:
    """Replace JSON-unsafe control characters in raw file content so parsing can succeed."""
    return _JSON_UNSAFE_RE.sub("\uFFFD", raw)


def _strip_sensitive(obj: Any) -> Any:
    """Recursively remove credential-like keys from a Node-RED node object."""
    if isinstance(obj, dict):
        return {
            k: _strip_sensitive(v)
            for k, v in obj.items()
            if k not in _FLOW_STRIP_KEYS
        }
    if isinstance(obj, list):
        return [_strip_sensitive(v) for v in obj]
    return obj


def refine_flow_content(flow_str: str) -> list[Any] | str:
    """
    Parse the embedded flow JSON string, strip credentials/sensitive keys from each node.
    Returns the cleaned list of nodes (so it serializes as real JSON array, not \"...\"),
    or "[invalid]" on parse failure.
    """
    if not flow_str or not flow_str.strip():
        return []
    raw = repair_json_string(flow_str)
    try:
        flow_data = json.loads(raw)
    except json.JSONDecodeError:
        return "[invalid]"
    if not isinstance(flow_data, list):
        return "[invalid]"
    return [_strip_sensitive(n) for n in flow_data]


def load_json_maybe_repaired(path: Path) -> list[Any] | None:
    """Load a JSON array file; if invalid, repair control chars and retry once."""
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = repair_json_string(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def refine_flow_item(
    item: dict[str, Any],
    *,
    keep_flow: bool = True,
    refine_embedded_flow: bool = True,
    readme_max: int | None = None,
    essential_only: bool = True,
) -> dict[str, Any]:
    """
    Return a refined copy of a flow library entry.
    - If keep_flow and refine_embedded_flow: parse 'flow' JSON, strip credentials, re-serialize.
    - If not keep_flow: replace 'flow' with '[truncated]'.
    - Optionally truncate 'readme' when readme_max is set.
    - If essential_only: keep only _id, url, created_at, updated_at, flow, readme, summary, gitOwners.
    """
    out = dict(item)
    if "flow" in out:
        raw = out.get("flow") or ""
        if not keep_flow:
            out["flow"] = "[truncated]" if raw else []
        elif refine_embedded_flow and raw:
            out["flow"] = refine_flow_content(raw)  # list of nodes or "[invalid]"
    if readme_max is not None and readme_max >= 0 and "readme" in out:
        r = _to_string(out["readme"])
        if len(r) > readme_max:
            out["readme"] = r[:readme_max] + "..."
        else:
            out["readme"] = r
    elif "readme" in out and out["readme"] is not None and not isinstance(out["readme"], str):
        out["readme"] = _to_string(out["readme"])
    if "summary" in out and out["summary"] is not None and not isinstance(out["summary"], str):
        out["summary"] = _to_string(out["summary"])
    if essential_only:
        out = {k: out[k] for k in FLOW_ESSENTIAL_KEYS if k in out}
    return out


def trim_node_item(item: dict[str, Any], readme_max: int = 2000) -> dict[str, Any]:
    """Light copy for nodes: truncate readme, keep metadata. readme can be string or parsed JSON."""
    out = dict(item)
    if "readme" in out:
        r = _to_string(out["readme"])
        if readme_max >= 0 and len(r) > readme_max:
            out["readme"] = r[:readme_max] + "..."
        else:
            out["readme"] = r
    return out


def trim_collection_item(item: dict[str, Any]) -> dict[str, Any]:
    """Light copy for collections (already fairly small)."""
    return dict(item)


def refine_list(
    items: list[Any],
    *,
    key_id: str = "_id",
    trim_item: Any = None,
) -> list[Any]:
    """Dedupe by key_id (keep last), optionally trim each item."""
    seen: set[str] = set()
    result: list[Any] = []
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        kid = item.get(key_id)
        if kid is None or kid in seen:
            continue
        seen.add(str(kid))
        if trim_item:
            item = trim_item(item)
        result.append(item)
    result.reverse()
    return result


def process_file(
    path: Path,
    out_path: Path,
    *,
    trim_item: Any = None,
    key_id: str = "_id",
) -> int:
    """Load (repairing if needed), refine, write. Returns count or -1 on failure."""
    data = load_json_maybe_repaired(path)
    if data is None:
        print(f"  Failed to load (invalid JSON): {path}")
        return -1
    if not isinstance(data, list):
        print(f"  Unexpected type {type(data)}: {path}")
        return -1
    refined = refine_list(data, key_id=key_id, trim_item=trim_item)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(refined, f, ensure_ascii=False, indent=2)
    print(f"  {path.name} -> {out_path.name} ({len(refined)} items)")
    return len(refined)


def main() -> None:
    p = argparse.ArgumentParser(description="Refine downloaded Node-RED library JSON (repair + optional trim)")
    p.add_argument("--data-dir", type=Path, default=Path("mydata"), help="Directory with node-red-library-*.json")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: same as --data-dir)",
    )
    p.add_argument(
        "--trim",
        action="store_true",
        help="Trim heavy fields: drop 'flow' body, truncate 'readme'",
    )
    p.add_argument(
        "--summary",
        action="store_true",
        help="Same as --trim but more aggressive: short readme (500 chars), flow dropped",
    )
    p.add_argument(
        "--suffix",
        type=str,
        default="-refined",
        help="Suffix for output filenames (default: -refined)",
    )
    p.add_argument(
        "--keep-all-fields",
        action="store_true",
        help="For flows: keep all fields (default: keep only _id, url, created_at, updated_at, flow, readme, summary, gitOwners)",
    )
    args = p.parse_args()

    data_dir = args.data_dir.resolve()
    out_dir = (args.out_dir or data_dir).resolve()
    if not data_dir.is_dir():
        p.error(f"Not a directory: {data_dir}")

    readme_max = 2000
    keep_flow = True
    if args.summary:
        readme_max = 500
        keep_flow = False
    elif args.trim:
        readme_max = 2000
        keep_flow = False

    flows_path = data_dir / "node-red-library-flows.json"
    collections_path = data_dir / "node-red-library-collections.json"
    nodes_path = data_dir / "node-red-library-nodes.json"
    catalogue_path = data_dir / "node-red-catalogue.json"

    print("Refining Node-RED library data\n")

    if flows_path.exists():
        # Always refine flow entries: parse embedded flow JSON, strip credentials, keep only essential keys
        trim_fn = lambda i: refine_flow_item(
            i,
            keep_flow=keep_flow,
            refine_embedded_flow=True,
            readme_max=readme_max if (args.trim or args.summary) else None,
            essential_only=not args.keep_all_fields,
        )
        process_file(
            flows_path,
            out_dir / f"node-red-library-flows{args.suffix}.json",
            trim_item=trim_fn,
        )
    else:
        print(f"  Skip (not found): {flows_path}")

    if collections_path.exists():
        trim_fn = trim_collection_item if (args.trim or args.summary) else None
        process_file(
            collections_path,
            out_dir / f"node-red-library-collections{args.suffix}.json",
            trim_item=trim_fn,
        )
    else:
        print(f"  Skip (not found): {collections_path}")

    if nodes_path.exists():
        trim_fn = (
            (lambda i: trim_node_item(i, readme_max=readme_max))
            if (args.trim or args.summary)
            else None
        )
        process_file(
            nodes_path,
            out_dir / f"node-red-library-nodes{args.suffix}.json",
            trim_item=trim_fn,
        )
    elif catalogue_path.exists():
        # Alternative: node-red-catalogue.json has {"name", "updated_at", "modules": [...]}
        raw = catalogue_path.read_text(encoding="utf-8", errors="replace")
        raw = repair_json_string(raw)
        try:
            cat = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  Skip (invalid JSON): {catalogue_path}")
        else:
            if isinstance(cat, dict) and "modules" in cat:
                trim_fn = (
                    (lambda i: trim_node_item(i, readme_max=readme_max))
                    if (args.trim or args.summary)
                    else None
                )
                modules = refine_list(
                    cat["modules"] if isinstance(cat.get("modules"), list) else [],
                    key_id="id",
                    trim_item=trim_fn,
                )
                out = {"name": cat.get("name", "Node-RED Community catalogue"), "updated_at": cat.get("updated_at"), "modules": modules}
                out_path = out_dir / f"node-red-catalogue{args.suffix}.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)
                print(f"  {catalogue_path.name} -> {out_path.name} ({len(modules)} modules)")
            else:
                print(f"  Skip (no 'modules' list): {catalogue_path}")
    else:
        print(f"  Skip (not found): {nodes_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
