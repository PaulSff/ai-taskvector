"""
Test assistant apply: graph edit and config edit → normalizer → canonical.
"""
from pathlib import Path

from normalizer import load_process_graph_from_file, load_training_config_from_file
from assistants import process_assistant_apply, training_assistant_apply


def test_process_assistant_no_edit():
    base = Path(__file__).resolve().parent / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    edit = {"action": "no_edit", "reason": "no change"}
    result = process_assistant_apply(graph, edit)
    assert result.environment_type.value == "thermodynamic"
    assert len(result.units) == len(graph.units)
    assert len(result.connections) == len(graph.connections)


def test_process_assistant_add_unit():
    base = Path(__file__).resolve().parent / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    n_units = len(graph.units)
    edit = {
        "action": "add_unit",
        "unit": {
            "id": "extra_valve",
            "type": "Valve",
            "controllable": True,
            "params": {},
        },
    }
    result = process_assistant_apply(graph, edit)
    assert len(result.units) == n_units + 1
    assert result.get_unit("extra_valve") is not None
    assert result.get_unit("extra_valve").type == "Valve"


def test_process_assistant_connect():
    base = Path(__file__).resolve().parent / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    n_conn = len(graph.connections)
    edit = {"action": "connect", "from": "hot_source", "to": "cold_valve"}
    result = process_assistant_apply(graph, edit)
    assert len(result.connections) == n_conn + 1
    pairs = [(c.from_id, c.to_id) for c in result.connections]
    assert ("hot_source", "cold_valve") in pairs


def test_training_assistant_no_edit():
    base = Path(__file__).resolve().parent / "config" / "examples" / "training_config.yaml"
    config = load_training_config_from_file(base)
    edit = {"action": "no_edit", "reason": "no change"}
    result = training_assistant_apply(config, edit)
    assert result.goal.target_temp == config.goal.target_temp
    assert result.hyperparameters.learning_rate == config.hyperparameters.learning_rate


def test_training_assistant_merge():
    base = Path(__file__).resolve().parent / "config" / "examples" / "training_config.yaml"
    config = load_training_config_from_file(base)
    edit = {"rewards": {"weights": {"dumping": -0.2}}}
    result = training_assistant_apply(config, edit)
    assert result.rewards.weights["dumping"] == -0.2
    assert result.goal.target_temp == config.goal.target_temp


if __name__ == "__main__":
    test_process_assistant_no_edit()
    test_process_assistant_add_unit()
    test_process_assistant_connect()
    test_training_assistant_no_edit()
    test_training_assistant_merge()
    print("All assistant tests passed.")
