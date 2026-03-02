#!/usr/bin/env python3
"""
Test import -> (canonical) -> export -> re-import roundtrip for Node-RED and n8n workflows.

Walks mydata/node-red/workflows and mydata/n8n/workflows, loads each JSON, runs through
to_process_graph -> from_process_graph -> to_process_graph, and asserts that structure
and key fields are preserved (units, connections, metadata, code_blocks, unit names/params).

Usage:
  python scripts/test_workflow_roundtrip.py
  MAX_PER_DIR=5 python scripts/test_workflow_roundtrip.py   # limit to 5 files per directory
  MAX_PER_DIR=0 python scripts/test_workflow_roundtrip.py   # run all (can be slow)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from normalizer import to_process_graph
from normalizer.export import from_process_graph
from schemas.process_graph import ProcessGraph


# Default: cap files per directory so CI stays fast; set MAX_PER_DIR=0 to run all
DEFAULT_MAX_PER_DIR = 30
MYDATA_NODE_RED = REPO_ROOT / "mydata" / "node-red" / "workflows"
MYDATA_N8N = REPO_ROOT / "mydata" / "n8n" / "workflows"


def _max_per_dir() -> int:
    try:
        v = os.environ.get("MAX_PER_DIR", str(DEFAULT_MAX_PER_DIR))
        return int(v) if v else 0
    except ValueError:
        return DEFAULT_MAX_PER_DIR


def _collect_json_paths(root: Path, max_files: int) -> list[Path]:
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for p in sorted(root.rglob("*.json")):
        if p.is_file():
            paths.append(p)
            if max_files and len(paths) >= max_files:
                break
    return paths


def _graph_signature(g: ProcessGraph) -> dict:
    """Minimal comparable signature: counts, unit ids/types/names, connection pairs, metadata keys, code_block ids."""
    units = [(u.id, u.type, (u.name or "").strip() or None) for u in g.units]
    conns = [(c.from_id, c.to_id) for c in g.connections]
    meta_keys = sorted(g.metadata.keys()) if getattr(g, "metadata", None) and isinstance(g.metadata, dict) else []
    code_ids = [b.id for b in g.code_blocks] if g.code_blocks else []
    return {
        "n_units": len(g.units),
        "n_connections": len(g.connections),
        "n_code_blocks": len(g.code_blocks or []),
        "unit_ids": sorted(u[0] for u in units),
        "unit_types": dict((u[0], u[1]) for u in units),
        "unit_names": dict((u[0], u[2]) for u in units if u[2] is not None),
        "connections": sorted(conns),
        "metadata_keys": meta_keys,
        "code_block_ids": sorted(code_ids),
    }


def _params_keys(unit_id: str, g: ProcessGraph) -> set[str]:
    u = g.get_unit(unit_id)
    if not u or not getattr(u, "params", None):
        return set()
    return set(u.params.keys())


def _assert_roundtrip_preserved(
    path: Path,
    format: str,
    graph1: ProcessGraph,
    graph2: ProcessGraph,
) -> None:
    """Assert that graph2 (after roundtrip) preserves structure and key data from graph1."""
    s1 = _graph_signature(graph1)
    s2 = _graph_signature(graph2)
    assert s1["n_units"] == s2["n_units"], f"{path}: unit count changed {s1['n_units']} -> {s2['n_units']}"
    assert s1["n_connections"] == s2["n_connections"], (
        f"{path}: connection count changed {s1['n_connections']} -> {s2['n_connections']}"
    )
    assert s1["unit_ids"] == s2["unit_ids"], f"{path}: unit ids differ"
    assert s1["connections"] == s2["connections"], f"{path}: connections differ"
    # Export may omit internal keys (e.g. _id); require graph2 keys ⊆ graph1 and values match for common keys
    set1, set2 = set(s1["metadata_keys"]), set(s2["metadata_keys"])
    assert set2 <= set1, (
        f"{path}: metadata has extra keys in roundtrip: {set2 - set1}"
    )
    assert s1["n_code_blocks"] == s2["n_code_blocks"], (
        f"{path}: code_blocks count changed {s1['n_code_blocks']} -> {s2['n_code_blocks']}"
    )
    assert s1["code_block_ids"] == s2["code_block_ids"], f"{path}: code_block ids differ"
    for uid in s1["unit_ids"]:
        assert s1["unit_types"].get(uid) == s2["unit_types"].get(uid), f"{path}: unit {uid} type changed"
        n1, n2 = s1["unit_names"].get(uid), s2["unit_names"].get(uid)
        assert n1 == n2, f"{path}: unit {uid} name changed {n1!r} -> {n2!r}"
    for uid in s1["unit_ids"]:
        p1 = _params_keys(uid, graph1)
        p2 = _params_keys(uid, graph2)
        # Export may add keys (e.g. unitType, func, params); require no loss of original keys
        assert p1 <= p2, f"{path}: unit {uid} params keys lost: {p1 - p2}"
    for k in s2["metadata_keys"]:
        v1 = (graph1.metadata or {}).get(k)
        v2 = (graph2.metadata or {}).get(k)
        if v1 != v2 and not (v1 is None and v2 is None):
            if isinstance(v1, (list, tuple)) and isinstance(v2, (list, tuple)) and len(v1) == len(v2):
                if all(a == b for a, b in zip(v1, v2)):
                    continue
            raise AssertionError(f"{path}: metadata[{k!r}] changed {v1!r} -> {v2!r}")


def _run_one(path: Path, format: str) -> str | None:
    """Run import -> export -> re-import for one file. Returns None on success, error message on failure."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return f"load: {e}"
    if not isinstance(raw, (dict, list)):
        return "not dict or list"
    try:
        graph1 = to_process_graph(raw, format=format)
    except Exception as e:
        return f"import: {e}"
    if not graph1.units:
        return None  # skip empty flows
    try:
        exported = from_process_graph(graph1, format=format)
    except Exception as e:
        return f"export: {e}"
    if exported is None:
        return "export returned None"
    try:
        graph2 = to_process_graph(exported, format=format)
    except Exception as e:
        return f"re-import: {e}"
    try:
        _assert_roundtrip_preserved(path, format, graph1, graph2)
    except AssertionError as e:
        return str(e)
    return None


def run_node_red(max_per_dir: int) -> tuple[int, int, list[tuple[Path, str]]]:
    """Run roundtrip on Node-RED workflows. Returns (ok, total, failures)."""
    paths = _collect_json_paths(MYDATA_NODE_RED, max_per_dir)
    failures: list[tuple[Path, str]] = []
    for path in paths:
        err = _run_one(path, "node_red")
        if err:
            failures.append((path, err))
    return len(paths) - len(failures), len(paths), failures


def run_n8n(max_per_dir: int) -> tuple[int, int, list[tuple[Path, str]]]:
    """Run roundtrip on n8n workflows. Returns (ok, total, failures)."""
    paths = _collect_json_paths(MYDATA_N8N, max_per_dir)
    failures: list[tuple[Path, str]] = []
    for path in paths:
        err = _run_one(path, "n8n")
        if err:
            failures.append((path, err))
    return len(paths) - len(failures), len(paths), failures


def main() -> int:
    max_per = _max_per_dir()
    print(f"Workflow roundtrip test (import -> export -> re-import); max per dir: {max_per or 'all'}")
    print()

    ok_nr, total_nr, fail_nr = run_node_red(max_per)
    print(f"Node-RED: {ok_nr}/{total_nr} passed")
    for path, msg in fail_nr[:10]:
        print(f"  FAIL {path.relative_to(REPO_ROOT)}: {msg}")
    if len(fail_nr) > 10:
        print(f"  ... and {len(fail_nr) - 10} more")
    print()

    ok_n8n, total_n8n, fail_n8n = run_n8n(max_per)
    print(f"n8n: {ok_n8n}/{total_n8n} passed")
    for path, msg in fail_n8n[:10]:
        print(f"  FAIL {path.relative_to(REPO_ROOT)}: {msg}")
    if len(fail_n8n) > 10:
        print(f"  ... and {len(fail_n8n) - 10} more")
    print()

    total_ok = ok_nr + ok_n8n
    total_all = total_nr + total_n8n
    total_fail = len(fail_nr) + len(fail_n8n)
    if total_fail:
        print(f"Total: {total_ok}/{total_all} passed, {total_fail} failed")
        return 1
    print(f"Total: {total_ok}/{total_all} passed")
    return 0


def test_node_red_roundtrip(max_per_dir: int | None = None):
    """Pytest: run Node-RED roundtrip on sample of workflows."""
    n = max_per_dir if max_per_dir is not None else _max_per_dir()
    ok, total, failures = run_node_red(n)
    assert not failures, f"Node-RED roundtrip: {len(failures)}/{total} failed: {failures[:5]}"


def test_n8n_roundtrip(max_per_dir: int | None = None):
    """Pytest: run n8n roundtrip on sample of workflows."""
    n = max_per_dir if max_per_dir is not None else _max_per_dir()
    ok, total, failures = run_n8n(n)
    assert not failures, f"n8n roundtrip: {len(failures)}/{total} failed: {failures[:5]}"


if __name__ == "__main__":
    sys.exit(main())
