#!/usr/bin/env python3
"""Smoke test for deploy.oracle_inject module. Run from repo root: python scripts/test_oracle_inject.py"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from deploy.oracle_inject import inject_oracle_into_flow, inject_oracle_into_process_graph
from schemas.process_graph import ProcessGraph


def test_inject_oracle_into_flow():
    flow = [
        {"id": "flow_main", "type": "tab", "label": "Main"},
        {"id": "n1", "type": "inject", "z": "flow_main"},
    ]
    out = inject_oracle_into_flow(flow, template="thermodynamic")
    nodes = [n for n in out if isinstance(n, dict) and n.get("type") == "function"]
    assert len(nodes) == 1
    assert nodes[0].get("unitType") == "RLOracle"
    assert "observation" in (nodes[0].get("func") or "")
    assert nodes[0].get("outputs") == 2


def test_inject_oracle_into_process_graph():
    graph = ProcessGraph(units=[], connections=[])
    pg = inject_oracle_into_process_graph(graph, template="thermodynamic")
    assert any(u.type == "RLOracle" for u in pg.units)
    assert any(cb.language == "javascript" for cb in pg.code_blocks)
    assert len(pg.code_blocks) >= 1
    cb = next(cb for cb in pg.code_blocks if cb.language == "javascript")
    assert "PARAMS" in cb.source
    assert "observation" in cb.source


if __name__ == "__main__":
    test_inject_oracle_into_flow()
    print("inject_oracle_into_flow: OK")
    test_inject_oracle_into_process_graph()
    print("inject_oracle_into_process_graph: OK")
    print("All tests passed.")
