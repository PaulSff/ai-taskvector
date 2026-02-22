#!/usr/bin/env python3
"""Smoke test for deploy.oracle_inject (universal Oracle, params from adapter_config)."""
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from deploy.agent_inject import inject_agent_template_into_flow
from deploy.oracle_inject import (
    inject_oracle_into_flow,
    inject_oracle_into_n8n_flow,
    inject_oracle_into_process_graph,
)
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

    # Python (PyFlow) Oracle
    pg_py = inject_oracle_into_process_graph(
        graph, adapter_config,
        observation_source_ids=["sensor1", "sensor2"],
        language="python",
    )
    cbs_py = [cb for cb in pg_py.code_blocks if cb.language == "python"]
    assert len(cbs_py) == 2


def test_pyflow_oracle_mode():
    """Run PyFlow adapter with Oracle units (step_driver + collector)."""
    adapter_config = {
        "observation_spec": [{"name": "temp"}],
        "action_spec": [{"name": "valve"}],
        "reward_config": {"type": "setpoint", "observation_index": 0, "target": 25.0},
        "max_steps": 10,
        "observation_sources": ["src1"],
    }
    graph = ProcessGraph(
        units=[
            {"id": "src1", "type": "Source", "controllable": False, "params": {"temp": 20.0}},
        ],
        connections=[],
    )
    pg = inject_oracle_into_process_graph(
        graph, adapter_config,
        observation_source_ids=["src1"],
        language="python",
    )
    raw = {
        "environment_type": "thermodynamic",
        "units": [u.model_dump() for u in pg.units],
        "connections": [{"from": c.from_id, "to": c.to_id} for c in pg.connections],
        "code_blocks": [{"id": b.id, "language": b.language, "source": b.source} for b in pg.code_blocks],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(raw, f)
        path = f.name
    try:
        from environments.external.pyflow_adapter import load_pyflow_env

        env = load_pyflow_env({
            "flow_path": path,
            "adapter_config": adapter_config,
        })
        obs, info = env.reset()
        assert obs.shape == (1,), f"obs.shape={obs.shape}"
        obs, reward, term, trunc, info = env.step([0.5])
        assert obs.shape == (1,)
        assert isinstance(reward, float)
        assert isinstance(term, bool)
    finally:
        Path(path).unlink(missing_ok=True)


def test_inject_oracle_into_n8n_flow():
    adapter_config = {
        "observation_spec": [{"name": "obs0"}, {"name": "obs1"}],
        "action_spec": [{"name": "act0"}],
        "reward_config": {"type": "setpoint", "target": 0.5},
    }
    flow = {"nodes": [], "connections": {}}
    inject_oracle_into_n8n_flow(flow, adapter_config)
    names = [n.get("name") for n in flow["nodes"] if isinstance(n, dict)]
    assert "rloracle_step_driver" in names
    assert "rloracle_collector" in names
    assert "rloracle_webhook" in names
    assert "rloracle_merge" in names
    step_driver = next(n for n in flow["nodes"] if n.get("name") == "rloracle_step_driver")
    assert "obs0" in (step_driver.get("parameters") or {}).get("jsCode", "")


def test_inject_agent_template_into_flow():
    adapter_config = {
        "observation_spec": [{"name": "thermometer_cold"}, {"name": "thermometer_hot"}, {"name": "thermometer_tank"}],
        "action_spec": [{"name": "cold_valve"}, {"name": "hot_valve"}],
    }
    flow = [{"id": "flow_main", "type": "tab"}, {"id": "s1", "type": "function", "wires": [[]]}]
    out = inject_agent_template_into_flow(
        flow,
        agent_id="rl_agent_1",
        model_path="models/test/best_model.zip",
        observation_source_ids=["s1"],
        action_target_ids=["v1"],
        adapter_config=adapter_config,
        inference_url="http://127.0.0.1:8000/predict",
    )
    funcs = [n for n in out if isinstance(n, dict) and n.get("type") == "function"]
    assert len(funcs) >= 2  # prepare + parse
    http_nodes = [n for n in out if isinstance(n, dict) and n.get("type") == "http request"]
    assert len(http_nodes) == 1
    prepare = next(n for n in funcs if "prepare" in (n.get("name") or ""))
    assert "thermometer_cold" in (prepare.get("func") or "")
    assert "8000/predict" in (prepare.get("func") or "")


if __name__ == "__main__":
    test_inject_oracle_into_flow()
    print("inject_oracle_into_flow: OK")
    test_inject_oracle_into_process_graph()
    print("inject_oracle_into_process_graph: OK")
    test_pyflow_oracle_mode()
    print("test_pyflow_oracle_mode: OK")
    test_inject_oracle_into_n8n_flow()
    print("inject_oracle_into_n8n_flow: OK")
    test_inject_agent_template_into_flow()
    print("inject_agent_template_into_flow: OK")
    print("All tests passed.")
