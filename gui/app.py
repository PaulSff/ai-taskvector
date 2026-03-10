"""
Constructor GUI: process graph, training config, run training / test policy.
Run from repo root: streamlit run gui/app.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
import yaml

from core.normalizer import load_process_graph_from_file, load_training_config_from_file, to_process_graph, to_training_config
from core.schemas.process_graph import ProcessGraph

# Optional React Flow visualization (streamlit-flow-component)
try:
    from streamlit_flow import streamlit_flow
    from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
    from streamlit_flow.state import StreamlitFlowState
    _HAS_STREAMLIT_FLOW = True
except ImportError:
    _HAS_STREAMLIT_FLOW = False
    StreamlitFlowState = None  # type: ignore[misc, assignment]


def _layered_layout(unit_list: list, conn_list: list) -> dict[str, tuple[float, float]]:
    """Assign positions with a left-to-right layered layout to reduce edge crossings.
    Sources on the left, sinks on the right; order within each layer by predecessor
    positions (barycenter heuristic).
    """
    unit_ids = [u.id for u in unit_list]
    id_to_idx = {uid: i for i, uid in enumerate(unit_ids)}
    preds: dict[str, list[str]] = {uid: [] for uid in unit_ids}
    for c in conn_list:
        if c.from_id in id_to_idx and c.to_id in id_to_idx and c.from_id != c.to_id:
            preds[c.to_id].append(c.from_id)

    # Assign layers: layer 0 = no predecessors; layer k+1 = all preds in layers 0..k
    layers: list[list[str]] = []
    assigned: set[str] = set()

    def has_all_preds_assigned(uid: str) -> bool:
        return all(p in assigned for p in preds[uid])

    while len(assigned) < len(unit_ids):
        layer = [uid for uid in unit_ids if uid not in assigned and has_all_preds_assigned(uid)]
        if not layer:
            layer = [uid for uid in unit_ids if uid not in assigned]
        for uid in layer:
            assigned.add(uid)
        layers.append(layer)

    # Order within each layer by barycenter (avg index of predecessors in previous layer)
    for layer_idx in range(1, len(layers)):
        prev_layer = layers[layer_idx - 1]
        prev_order = {uid: i for i, uid in enumerate(prev_layer)}

        def key(uid: str) -> float:
            p = preds[uid]
            if not p:
                return 0.0
            return sum(prev_order.get(x, 0) for x in p) / len(p)

        layers[layer_idx] = sorted(layers[layer_idx], key=key)

    # Position: left-to-right by layer; within each layer, vertical strip centered
    dx, dy = 260.0, 100.0
    x0, y0 = 80.0, 60.0
    positions: dict[str, tuple[float, float]] = {}
    for li, layer in enumerate(layers):
        base_y = y0 - (len(layer) - 1) * dy / 2 if layer else 0.0
        for ni, uid in enumerate(layer):
            positions[uid] = (x0 + li * dx, base_y + ni * dy)
    return positions


def _process_graph_to_flow_state(graph: ProcessGraph) -> "StreamlitFlowState":
    """Convert canonical ProcessGraph to StreamlitFlowState with a layered layout to minimize edge crossings."""
    if not _HAS_STREAMLIT_FLOW:
        raise RuntimeError("streamlit-flow-component is not installed")
    unit_list = graph.units
    conn_list = graph.connections
    positions = _layered_layout(unit_list, conn_list)
    nodes = []
    for u in unit_list:
        pos = positions.get(u.id, (100.0, 100.0))
        label = f"**{u.type}**\n{u.id}" + ("\n(control)" if u.controllable else "")
        nodes.append(
            StreamlitFlowNode(
                id=u.id,
                pos=pos,
                data={"content": label},
                node_type="default",
                source_position="right",
                target_position="left",
            )
        )
    edges = []
    for j, c in enumerate(conn_list):
        edges.append(
            StreamlitFlowEdge(
                id=f"e_{c.from_id}_{c.to_id}_{j}",
                source=c.from_id,
                target=c.to_id,
            )
        )
    return StreamlitFlowState(nodes=nodes, edges=edges)


# Page config
st.set_page_config(page_title="RL Agent gym", layout="wide")

st.title("RL Agent gym")
st.caption("Process graph (Node-RED, PyFlow, Ryven, n8n, YAML) + training config → run training / test policy")

# Sidebar: process graph source
st.sidebar.header("Import Workflow")
process_source = st.sidebar.radio(
    "Load a workflow graph from",
    [
        "Example (temperature)",
        "Upload Node-RED JSON",
        "Upload YAML",
        "Upload PyFlow JSON",
        "Upload Ryven JSON",
        "Upload n8n JSON",
        "Paste Node-RED JSON",
        "Paste process graph",
    ],
    index=0,
)

process_graph = None
process_error = None
process_path_used = None
process_graph_load_key = None  # Identifies sidebar load so we don't overwrite chat-applied edits

if process_source == "Example (temperature)":
    example_path = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    if example_path.exists():
        try:
            process_graph = load_process_graph_from_file(example_path)
            process_path_used = str(example_path)
            process_graph_load_key = ("sidebar", process_source, process_path_used)
        except Exception as e:
            process_error = str(e)
    else:
        process_error = f"Example not found: {example_path}"

elif process_source == "Upload Node-RED JSON":
    uploaded = st.sidebar.file_uploader("Node-RED flow (JSON)", type=["json"])
    if uploaded:
        try:
            raw = json.load(uploaded)
            process_graph = to_process_graph(raw, format="node_red")
            process_graph_load_key = ("sidebar", process_source, uploaded.name, uploaded.size)
        except Exception as e:
            process_error = str(e)

elif process_source == "Upload YAML":
    uploaded = st.sidebar.file_uploader("Process graph (YAML)", type=["yaml", "yml"])
    if uploaded:
        try:
            raw = yaml.safe_load(uploaded)
            process_graph = to_process_graph(raw, format="dict")
            process_graph_load_key = ("sidebar", process_source, uploaded.name, uploaded.size)
        except Exception as e:
            process_error = str(e)

elif process_source == "Upload PyFlow JSON":
    uploaded = st.sidebar.file_uploader("PyFlow graph (JSON)", type=["json"])
    if uploaded:
        try:
            raw = json.load(uploaded)
            process_graph = to_process_graph(raw, format="pyflow")
            process_graph_load_key = ("sidebar", process_source, uploaded.name, uploaded.size)
        except Exception as e:
            process_error = str(e)

elif process_source == "Upload Ryven JSON":
    uploaded = st.sidebar.file_uploader("Ryven graph (JSON)", type=["json"])
    if uploaded:
        try:
            raw = json.load(uploaded)
            process_graph = to_process_graph(raw, format="ryven")
            process_graph_load_key = ("sidebar", process_source, uploaded.name, uploaded.size)
        except Exception as e:
            process_error = str(e)

elif process_source == "Upload n8n JSON":
    uploaded = st.sidebar.file_uploader("n8n workflow (JSON)", type=["json"])
    if uploaded:
        try:
            raw = json.load(uploaded)
            process_graph = to_process_graph(raw, format="n8n")
            process_graph_load_key = ("sidebar", process_source, uploaded.name, uploaded.size)
        except Exception as e:
            process_error = str(e)

elif process_source == "Paste Node-RED JSON":
    pasted = st.sidebar.text_area("Paste Node-RED flow JSON (array of nodes)")
    if pasted.strip():
        try:
            raw = json.loads(pasted)
            process_graph = to_process_graph(raw, format="node_red")
            process_graph_load_key = ("sidebar", process_source, len(pasted), pasted[:200])
        except Exception as e:
            process_error = str(e)

elif process_source == "Paste process graph":
    pasted = st.sidebar.text_area(
        "Paste JSON: { \"units\": [ { \"id\": \"...\", \"type\": \"...\", \"controllable\": false } ], \"connections\": [ { \"from\": \"id1\", \"to\": \"id2\" } ] }",
        height=120,
        placeholder='{"units": [...], "connections": [...]}',
    )
    if pasted.strip():
        try:
            raw = json.loads(pasted)
            if isinstance(raw, dict) and "units" in raw and "connections" in raw:
                process_graph = to_process_graph(raw, format="dict")
                process_graph_load_key = ("sidebar", process_source, len(pasted), pasted[:200])
            else:
                process_error = "JSON must have \"units\" and \"connections\" keys (assistant-style graph)."
        except json.JSONDecodeError as e:
            process_error = f"Invalid JSON: {e}"
        except Exception as e:
            process_error = str(e)

if process_error:
    st.sidebar.error(process_error)
if process_graph is not None:
    st.sidebar.success(f"Loaded: {len(process_graph.units)} units, {len(process_graph.connections)} connections")
    if process_path_used:
        st.sidebar.caption(process_path_used)

# Keep working copy in session_state; only overwrite when sidebar load actually changed (so Apply from chat persists)
if "process_graph_load_key" not in st.session_state:
    st.session_state.process_graph_load_key = None
if process_graph is not None and process_graph_load_key is not None:
    if st.session_state.process_graph_load_key != process_graph_load_key:
        st.session_state.process_graph = process_graph
        st.session_state.process_graph_load_key = process_graph_load_key
if "process_graph" not in st.session_state:
    st.session_state.process_graph = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_pending_reply" not in st.session_state:
    st.session_state.chat_pending_reply = False
if "training_config" not in st.session_state:
    st.session_state.training_config = None

process_graph = st.session_state.process_graph
training_config = st.session_state.training_config
if training_config is None:
    try:
        training_config = load_training_config_from_file(REPO_ROOT / "config" / "examples" / "training_config.yaml")
        st.session_state.training_config = training_config
    except Exception:
        pass

# Layout: main content (left) + AI chat panel (right); golden ratio φ ≈ 1.618 (main : chat = φ : 1)
_GOLDEN = 1.618
col_main, col_chat = st.columns([_GOLDEN, 1.0])

with col_main:
    tab_flow, tab_config, tab_run, tab_assistant = st.tabs(["Flow", "Training config", "Run / Test", "Assistant"])

with col_main:
    with tab_flow:
        st.header("Workflow")
        if process_graph is None:
            st.info("Load a process graph from the sidebar to see the flow visualization.")
        else:
            if not _HAS_STREAMLIT_FLOW:
                st.warning(
                    "Install **streamlit-flow-component** for React-Flow visualization: "
                    "`pip install streamlit-flow-component`"
                )
                st.caption("Units and connections (no diagram):")
                for u in process_graph.units:
                    st.text(f"{u.id}: {u.type}" + (" (controllable)" if u.controllable else ""))
                for c in process_graph.connections:
                    st.text(f"  {c.from_id} → {c.to_id}")
            else:
                graph_sig = (len(process_graph.units), len(process_graph.connections), tuple(u.id for u in process_graph.units))
                if "flow_state" not in st.session_state or st.session_state.get("flow_graph_sig") != graph_sig:
                    st.session_state.flow_state = _process_graph_to_flow_state(process_graph)
                    st.session_state.flow_graph_sig = graph_sig
                st.session_state.flow_state = streamlit_flow("process_flow", st.session_state.flow_state)
                st.caption("Pan, zoom, and move nodes. Edits in the canvas are not saved back to the process graph.")

    with tab_config:
        st.header("Training config")
        config_source = st.radio("Load training config from", ["Example (temperature)", "Example (Custom)", "Example (Node-RED)", "Example (PyFlow)", "Upload YAML"], horizontal=True)
        _config_path_used = None
        if config_source == "Example (temperature)":
            example_cfg = REPO_ROOT / "config" / "examples" / "training_config.yaml"
            if example_cfg.exists():
                try:
                    training_config = load_training_config_from_file(example_cfg)
                    st.session_state.training_config = training_config
                    _config_path_used = str(example_cfg)
                except Exception as e:
                    st.error(str(e))
        elif config_source == "Example (Custom)":
            example_cfg = REPO_ROOT / "config" / "examples" / "native_runtime_factory" / "native_AI_temperature-control-agent" / "training_config_native.yaml"
            if example_cfg.exists():
                try:
                    training_config = load_training_config_from_file(example_cfg)
                    st.session_state.training_config = training_config
                    _config_path_used = str(example_cfg)
                except Exception as e:
                    st.error(str(e))
            else:
                st.warning("File not found: config/examples/native_runtime_factory/.../training_config_native.yaml")
        elif config_source == "Example (Node-RED)":
            example_cfg = REPO_ROOT / "config" / "examples" / "node-red_runtime" / "node-red_AI_temperature-control-agent" / "training_config_node_red.yaml"
            if example_cfg.exists():
                try:
                    training_config = load_training_config_from_file(example_cfg)
                    st.session_state.training_config = training_config
                    _config_path_used = str(example_cfg)
                except Exception as e:
                    st.error(str(e))
            else:
                st.warning("File not found: config/examples/node-red_runtime/.../training_config_node_red.yaml")
        elif config_source == "Example (PyFlow)":
            example_cfg = REPO_ROOT / "config" / "examples" / "pyflow_runtime" / "pyflow_AI_temperature-control-agent" / "training_config_pyflow.yaml"
            if example_cfg.exists():
                try:
                    training_config = load_training_config_from_file(example_cfg)
                    st.session_state.training_config = training_config
                    _config_path_used = str(example_cfg)
                except Exception as e:
                    st.error(str(e))
            else:
                st.warning("File not found: config/examples/pyflow_runtime/.../training_config_pyflow.yaml")
        else:
            uploaded_cfg = st.file_uploader("Training config YAML", type=["yaml", "yml"], key="config_upload")
            if uploaded_cfg:
                try:
                    raw = yaml.safe_load(uploaded_cfg)
                    training_config = to_training_config(raw, format="dict")
                    st.session_state.training_config = training_config
                    _config_path_used = "(uploaded)"
                except Exception as e:
                    st.error(str(e))

        if training_config is not None:
            with st.expander("Goal", expanded=True):
                goal_temp = st.number_input("Target temperature (°C)", value=float(training_config.goal.target_temp or 37.0), key="goal_temp")
                vol_lo = st.number_input("Target volume ratio min", value=training_config.goal.target_volume_ratio[0] if training_config.goal.target_volume_ratio else 0.8, min_value=0.0, max_value=1.0, step=0.05, key="vol_lo")
                vol_hi = st.number_input("Target volume ratio max", value=training_config.goal.target_volume_ratio[1] if training_config.goal.target_volume_ratio else 0.85, min_value=0.0, max_value=1.0, step=0.05, key="vol_hi")
            with st.expander("Run / callbacks"):
                model_dir = st.text_input("Model directory (agent folder)", value=training_config.callbacks.model_dir or "models/temperature-control-agent", key="model_dir")
                total_timesteps = st.number_input("Total timesteps", value=training_config.total_timesteps, min_value=1000, step=10000, key="timesteps")
            with st.expander("Hyperparameters"):
                lr = st.number_input("Learning rate", value=float(training_config.hyperparameters.learning_rate), format="%.2e", key="lr")
                n_steps = st.number_input("n_steps (PPO)", value=training_config.hyperparameters.n_steps, key="n_steps")

            if st.button("Save config to file"):
                out_path = REPO_ROOT / "config" / "gui_training_config.yaml"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                updated = training_config.model_dump()
                updated["goal"]["target_temp"] = goal_temp
                updated["goal"]["target_volume_ratio"] = [vol_lo, vol_hi]
                updated["total_timesteps"] = int(total_timesteps)
                updated["callbacks"]["model_dir"] = model_dir
                updated["hyperparameters"]["learning_rate"] = lr
                updated["hyperparameters"]["n_steps"] = int(n_steps)
                with open(out_path, "w") as f:
                    yaml.dump(updated, f, default_flow_style=False, sort_keys=False)
                st.success(f"Saved to {out_path}")

    with tab_run:
        st.header("Run training / Test policy")
        _training_config = training_config
        if _training_config is None:
            try:
                _training_config = load_training_config_from_file(REPO_ROOT / "config" / "examples" / "training_config.yaml")
            except Exception:
                pass
        if _training_config is None:
            st.warning("Load a training config in the **Training config** tab first (Example or Upload YAML).")
        else:
            if process_graph is None and getattr(_training_config.environment, "source", "native") == "native":
                st.warning("Load a process graph from the sidebar for native env training. For Node-RED/external, a graph is optional.")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Run training")
                config_file = st.text_input("Training config path", value=str(REPO_ROOT / "config" / "examples" / "training_config.yaml"), key="train_config_path")
                process_config_file = st.text_input("Process config path (optional)", value=str(REPO_ROOT / "config" / "examples" / "temperature_process.yaml"), key="train_process_path")
                timesteps_override = st.number_input("Timesteps (override)", value=0, min_value=0, step=10000, help="0 = use config value")
                if st.button("Run training"):
                    # Resolve config path (may be relative to repo root)
                    cfg_path = Path(config_file)
                    if not cfg_path.is_absolute():
                        cfg_path = REPO_ROOT / config_file
                    if not cfg_path.exists():
                        st.error(f"Config file not found: {cfg_path}")
                    else:
                        cmd = [sys.executable, str(REPO_ROOT / "train.py"), "--config", str(cfg_path)]
                        if process_config_file:
                            proc_path = Path(process_config_file)
                            if not proc_path.is_absolute():
                                proc_path = REPO_ROOT / process_config_file
                            if proc_path.exists():
                                cmd += ["--process-config", str(proc_path)]
                        if timesteps_override > 0:
                            cmd += ["--timesteps", str(timesteps_override)]
                        st.code(" ".join(cmd))
                        try:
                            with st.spinner("Training... (this can take several minutes)"):
                                out = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=3600)
                            if out.returncode == 0:
                                st.success("Training finished.")
                                if out.stdout:
                                    st.text_area("Stdout", out.stdout, height=200)
                            else:
                                st.error("Training failed.")
                                if out.stderr:
                                    st.text_area("Stderr", out.stderr, height=200)
                        except subprocess.TimeoutExpired:
                            st.error("Training timed out (1 hour). Run from terminal for longer runs.")
                        except Exception as e:
                            st.error(f"Error running training: {e}")
            with col2:
                st.subheader("Test policy")
                model_path = st.text_input("Model path", value=str(REPO_ROOT / "models" / "temperature-control-agent" / "best" / "best_model"), key="test_model_path")
                model_path_resolved = Path(model_path)
                model_exists = model_path_resolved.exists() or Path(str(model_path_resolved) + ".zip").exists()
                if not model_exists:
                    st.warning("Model file not found. Train first (Run training above) or set model path to an existing model (e.g. …/best/best_model.zip).")
                test_episodes = st.number_input("Episodes", value=5, min_value=1, key="test_episodes")
                if st.button("Test policy"):
                    cmd = [sys.executable, str(REPO_ROOT / "test_model.py"), model_path, "--episodes", str(test_episodes)]
                    st.code(" ".join(cmd))
                    with st.spinner("Testing..."):
                        out = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
                    if out.returncode == 0:
                        st.success("Test finished.")
                        if out.stdout:
                            st.text_area("Output", out.stdout, height=200, key="test_stdout")
                    else:
                        st.error("Test failed.")
                        if out.stderr:
                            st.text_area("Stderr", out.stderr, height=200, key="test_stderr")

    with tab_assistant:
        st.header("Assistant (apply edits)")
        st.caption("Apply Workflow Designer or RL Coach edit JSON; or use the **AI chat** panel on the right.")
        edit_type = st.radio("Edit type", ["Process graph", "Training config"], horizontal=True)
        edit_json = st.text_area("Edit JSON (e.g. {\"action\": \"add_unit\", \"unit\": {...}} or {\"rewards\": {\"weights\": {\"dumping\": -0.2}}}")
        if st.button("Apply edit"):
            if not edit_json.strip():
                st.warning("Paste an edit JSON.")
            else:
                try:
                    edit = json.loads(edit_json)
                    if edit_type == "Process graph":
                        if process_graph is None:
                            st.warning("Load a process graph first (sidebar).")
                        else:
                            from assistants.edit_workflows.runner import apply_edit_via_workflow
                            result = apply_edit_via_workflow(process_graph, edit)
                            st.session_state.process_graph = result
                            st.success(f"Result: {len(result.units)} units, {len(result.connections)} connections")
                            st.json(result.model_dump(by_alias=True))
                    else:
                        _cfg = training_config or load_training_config_from_file(REPO_ROOT / "config" / "examples" / "training_config.yaml")
                        from assistants import training_assistant_apply
                        result = training_assistant_apply(_cfg, edit)
                        st.session_state.training_config = result
                        st.success("Config updated")
                        st.json(result.model_dump())
                except Exception as e:
                    st.error(str(e))

# Right column: AI chat panel
with col_chat:
    st.header("AI Chat")
    st.caption("Talk to **Workflow Designer** (process) or **RL Coach** (training). Requires Ollama.")
    chat_assistant = st.radio("Assistant", ["Workflow Designer", "RL Coach"], key="chat_assistant", label_visibility="collapsed")
    chat_model = st.text_input("Ollama model", value="llama3.2", key="chat_model")
    # Preflight: show Ollama status + model availability to avoid "no response" confusion.
    with st.expander("Ollama status", expanded=False):
        try:
            import ollama  # type: ignore

            try:
                models_resp = ollama.list()
                # ollama-python returns ListResponse with .models (list of Model); each has .model (name), not .name
                if hasattr(models_resp, "models"):
                    models = list(models_resp.models) if models_resp.models else []
                    names = [getattr(m, "model", None) or getattr(m, "name", None) for m in models]
                else:
                    models = models_resp.get("models", []) if isinstance(models_resp, dict) else []
                    names = [m.get("name") or m.get("model") for m in models if isinstance(m, dict) and (m.get("name") or m.get("model"))]
                names = [n for n in names if n]
                if names:
                    st.success("Connected to Ollama.")
                    st.caption("Installed models:")
                    st.code("\n".join(names))
                    if chat_model:
                        matched = any(n == chat_model or n.startswith(chat_model + ":") for n in names)
                        if not matched:
                            st.warning(
                                f"Model `{chat_model}` not in list. Use one of the names above or run: `ollama pull {chat_model}`"
                            )
                else:
                    st.warning("Connected to Ollama, but no models were listed.")
                    if chat_model:
                        st.caption(f"Try: `ollama pull {chat_model}`")
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                if "vocab only" in low or "skipping tensors" in low:
                    st.error(
                        "Ollama reported 'vocab only - skipping tensors' which usually means a corrupt/incomplete model pull."
                    )
                    st.caption("Fix: `ollama rm <model>` then `ollama pull <model>` and test with `ollama run <model> \"hello\"`.")
                else:
                    st.error("Couldn't query Ollama models.")
                    st.caption(msg)
        except Exception:
            st.warning("Python package `ollama` not available in this environment.")
            st.caption("Fix: `pip install ollama` (then start Ollama and pull a model, e.g. `ollama pull llama3.2`).")
    for i, msg in enumerate(st.session_state.chat_messages):
        with st.chat_message(msg["role"]):
            content = msg.get("content")
            st.markdown(content if content else "(No response)")
            if msg.get("edit_result"):
                st.caption(msg["edit_result"])
            # Apply button: only for assistant messages that have an unapplied edit
            if (
                msg.get("role") == "assistant"
                and msg.get("edit")
                and msg.get("edit", {}).get("action") != "no_edit"
                and not msg.get("edit_applied")
            ):
                if st.button("Apply", key=f"apply_chat_{i}"):
                    _pg = st.session_state.process_graph
                    _cfg = st.session_state.training_config
                    if _cfg is None and (REPO_ROOT / "config" / "examples" / "training_config.yaml").exists():
                        try:
                            _cfg = load_training_config_from_file(REPO_ROOT / "config" / "examples" / "training_config.yaml")
                        except Exception:
                            pass
                    assistant_type = msg.get("assistant_type") or chat_assistant
                    edit = msg["edit"]
                    try:
                        if assistant_type == "Workflow Designer":
                            if _pg is None:
                                st.session_state.chat_messages[i]["edit_result"] = "Load a process graph first."
                            else:
                                from assistants.edit_workflows.runner import apply_edit_via_workflow
                                result = apply_edit_via_workflow(_pg, edit)
                                st.session_state.process_graph = result
                                st.session_state.chat_messages[i]["edit_result"] = (
                                    f"Applied: {len(result.units)} units, {len(result.connections)} connections"
                                )
                                # Force flow diagram to rebuild on next run
                                if "flow_graph_sig" in st.session_state:
                                    del st.session_state["flow_graph_sig"]
                                if "flow_state" in st.session_state:
                                    del st.session_state["flow_state"]
                        else:
                            if _cfg is None:
                                st.session_state.chat_messages[i]["edit_result"] = "Load a training config first."
                            else:
                                from assistants import training_assistant_apply
                                result = training_assistant_apply(_cfg, edit)
                                st.session_state.training_config = result
                                st.session_state.chat_messages[i]["edit_result"] = "Config updated."
                    except Exception as e:
                        st.session_state.chat_messages[i]["edit_result"] = f"Apply failed: {e}"
                    st.session_state.chat_messages[i]["edit_applied"] = True
                    st.rerun()
                st.caption("Suggested edit — click **Apply** to use it.")

    # Step 1: user just submitted — append their message and schedule reply on next run
    chat_input = st.chat_input("Message the assistant…")
    if chat_input:
        st.session_state.chat_messages.append({"role": "user", "content": chat_input})
        st.session_state.chat_pending_reply = True
        st.rerun()

    # Step 2: we have a pending reply — generate it in this run so UI update is reliable
    if st.session_state.chat_pending_reply and st.session_state.chat_messages:
        last = st.session_state.chat_messages[-1]
        if last.get("role") == "user":
            st.session_state.chat_pending_reply = False
            user_content = last.get("content") or ""
            reply = ""
            edit_result = None
            _pg = st.session_state.process_graph
            _cfg = st.session_state.training_config
            if _cfg is None and (REPO_ROOT / "config" / "examples" / "training_config.yaml").exists():
                try:
                    _cfg = load_training_config_from_file(REPO_ROOT / "config" / "examples" / "training_config.yaml")
                except Exception:
                    pass
            try:
                with st.spinner("Thinking…"):
                    if chat_assistant == "Workflow Designer":
                        if _pg is None:
                            reply = "Load a process graph from the sidebar first."
                            edit = None
                        else:
                            from gui.chat import chat_workflow_designer
                            history = st.session_state.chat_messages[:-1]
                            reply, edit = chat_workflow_designer(
                                user_content, _pg, model=chat_model, chat_history=history
                            )
                    else:
                        if _cfg is None:
                            reply = "Load a training config in the Training config tab first."
                            edit = None
                        else:
                            from gui.chat import chat_rl_coach
                            history = st.session_state.chat_messages[:-1]
                            reply, edit = chat_rl_coach(
                                user_content, _cfg, model=chat_model, chat_history=history
                            )
            except Exception as e:
                reply = f"Error: {e}"
                edit = None
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": (reply or "(No response from model.)").strip(),
                "edit": edit,
                "assistant_type": chat_assistant,
                "edit_applied": False,
            })
            st.rerun()
    if st.button("Clear chat", key="clear_chat"):
        st.session_state.chat_messages = []
        st.session_state.chat_pending_reply = False
        st.rerun()

# Footer: show process graph summary if loaded
if process_graph is not None:
    st.sidebar.divider()
    st.sidebar.subheader("Units")
    for u in process_graph.units:
        st.sidebar.caption(f"{u.id}: {u.type}" + (" (controllable)" if u.controllable else ""))
