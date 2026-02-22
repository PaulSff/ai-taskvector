#!/usr/bin/env python3
"""Smoke test for deploy.oracle_inject (universal Oracle, params from adapter_config)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from deploy.oracle_inject import inject_oracle_into_flow, inject_oracle_into_process_graph
from schemas.process_graph import ProcessGraph


def test_inject_oracle_into_flow():
    adapter_config = {
        "observation_spec": [
            {"name": "thermometer_cold"},
            {"name": "thermometer_hot"},
            {"name": "thermometer_tank"},
            {"name": "water_level"},
        ],
        "action_spec": [{"name": "cold_valve"}, {"name": "dump_valve"}, {"name": "hot_valve"}],
        "reward_config": {"type": "setpoint", "observation_index": 2, "target": 0.37},
        "max_steps": 600,
    }
    flow = [
        {"id": "flow_main", "type": "tab", "label": "Main"},
        {"id": "n1", "type": "inject", "z": "flow_main"},
    ]
    out = inject_oracle_into_flow(flow, adapter_config)
    funcs = [n for n in out if isinstance(n, dict) and n.get("type") == "function"]
    assert len(funcs) >= 2  # step_driver + collector
    step_driver = next(n for n in funcs if n.get("unitType") == "RLOracle" and "step" in (n.get("name") or "").lower())
    assert "observation" in (step_driver.get("func") or "")
    assert "thermometer_cold" in (step_driver.get("func") or "")


def test_inject_oracle_into_process_graph():
    adapter_config = {
        "observation_spec": [{"name": "obs0"}, {"name": "obs1"}],
        "action_spec": [{"name": "act0"}],
        "reward_config": {"type": "setpoint", "target": 1.0},
    }
    graph = ProcessGraph(units=[], connections=[])
    pg = inject_oracle_into_process_graph(graph, adapter_config)
    oracles = [u for u in pg.units if u.type == "RLOracle"]
    assert len(oracles) == 2  # step_driver + collector
    assert len(pg.code_blocks) == 2
    for cb in pg.code_blocks:
        assert cb.language == "javascript"
        assert "observation" in cb.source


if __name__ == "__main__":
    test_inject_oracle_into_flow()
    print("inject_oracle_into_flow: OK")
    test_inject_oracle_into_process_graph()
    print("inject_oracle_into_process_graph: OK")
    print("All tests passed.")
