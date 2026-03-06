#!/usr/bin/env python3
"""Smoke test for deploy.oracle_inject (canonical Oracle code_blocks) and agent inject."""
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from deploy.agent_inject import inject_agent_template_into_flow
from deploy.oracle_inject import render_oracle_code_blocks_for_canonical
from schemas.process_graph import ProcessGraph, Unit, Connection, CodeBlock


def test_render_oracle_code_blocks_for_canonical_js():
    """Canonical Oracle: JS code_blocks for step_driver and step_rewards."""
    adapter_config = {
        "observation_spec": [{"name": "obs0"}, {"name": "obs1"}],
        "action_spec": [{"name": "act0"}],
        "reward_config": {"type": "setpoint", "target": 0.5},
        "max_steps": 100,
    }
    blocks = render_oracle_code_blocks_for_canonical(adapter_config, language="javascript")
    assert len(blocks) == 2
    ids = {b["id"] for b in blocks}
    assert ids == {"step_driver", "step_rewards"}
    for b in blocks:
        assert b["language"] == "javascript"
        assert "observation" in b["source"] or "action" in b["source"]


def test_render_oracle_code_blocks_for_canonical_py():
    """Canonical Oracle: Python code_blocks for step_driver and step_rewards."""
    adapter_config = {
        "observation_spec": [{"name": "temp"}],
        "action_spec": [{"name": "valve"}],
        "reward_config": {"type": "setpoint", "observation_index": 0, "target": 25.0},
        "max_steps": 10,
    }
    blocks = render_oracle_code_blocks_for_canonical(
        adapter_config, language="python", observation_source_ids=["sensor1"]
    )
    assert len(blocks) == 2
    assert blocks[0]["id"] == "step_driver"
    assert blocks[1]["id"] == "step_rewards"
    assert all(b["language"] == "python" for b in blocks)


def test_pyflow_oracle_mode_canonical():
    """PyFlow adapter with canonical topology (step_driver + step_rewards)."""
    from units.register_env_agnostic import register_env_agnostic_units
    register_env_agnostic_units()

    adapter_config = {
        "observation_spec": [{"name": "temp"}],
        "action_spec": [{"name": "valve"}],
        "reward_config": {"type": "setpoint", "observation_index": 0, "target": 25.0},
        "max_steps": 10,
    }
    code_blocks = render_oracle_code_blocks_for_canonical(
        adapter_config, language="python", observation_source_ids=["src1"]
    )
    graph = ProcessGraph(
        units=[
            Unit(id="src1", type="Source", controllable=False, params={"temp": 20.0}),
            Unit(id="step_driver", type="StepDriver", controllable=False, params={}),
            Unit(id="step_rewards", type="StepRewards", controllable=False, params={"max_steps": 10}),
        ],
        connections=[
            Connection(from_id="src1", to_id="step_rewards", from_port="0", to_port="0"),
        ],
        code_blocks=[CodeBlock(id=b["id"], language=b["language"], source=b["source"]) for b in code_blocks],
    )
    raw = {
        "environment_type": "thermodynamic",
        "units": [u.model_dump() for u in graph.units],
        "connections": [{"from": c.from_id, "to": c.to_id} for c in graph.connections],
        "code_blocks": [{"id": b.id, "language": b.language, "source": b.source} for b in graph.code_blocks],
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
    assert len(funcs) >= 2
    http_nodes = [n for n in out if isinstance(n, dict) and n.get("type") == "http request"]
    assert len(http_nodes) == 1
    prepare = next(n for n in funcs if "prepare" in (n.get("name") or ""))
    assert "thermometer_cold" in (prepare.get("func") or "")
    assert "8000/predict" in (prepare.get("func") or "")


if __name__ == "__main__":
    test_render_oracle_code_blocks_for_canonical_js()
    print("render_oracle_code_blocks_for_canonical (JS): OK")
    test_render_oracle_code_blocks_for_canonical_py()
    print("render_oracle_code_blocks_for_canonical (Python): OK")
    test_pyflow_oracle_mode_canonical()
    print("test_pyflow_oracle_mode_canonical: OK")
    test_inject_agent_template_into_flow()
    print("inject_agent_template_into_flow: OK")
    print("All tests passed.")
