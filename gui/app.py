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

from normalizer import load_process_graph_from_file, load_training_config_from_file
from normalizer.normalizer import to_process_graph, to_training_config

# Page config
st.set_page_config(page_title="Process RL Constructor", layout="wide")

st.title("Process RL Constructor")
st.caption("Process graph (Node-RED / YAML) + training config → run training / test policy")

# Sidebar: process graph source
st.sidebar.header("Process graph")
process_source = st.sidebar.radio(
    "Load process graph from",
    ["Example (temperature)", "Upload Node-RED JSON", "Upload YAML", "Paste JSON"],
    index=0,
)

process_graph = None
process_error = None
process_path_used = None

if process_source == "Example (temperature)":
    example_path = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    if example_path.exists():
        try:
            process_graph = load_process_graph_from_file(example_path)
            process_path_used = str(example_path)
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
        except Exception as e:
            process_error = str(e)

elif process_source == "Upload YAML":
    uploaded = st.sidebar.file_uploader("Process graph (YAML)", type=["yaml", "yml"])
    if uploaded:
        try:
            raw = yaml.safe_load(uploaded)
            process_graph = to_process_graph(raw, format="dict")
        except Exception as e:
            process_error = str(e)

elif process_source == "Paste JSON":
    pasted = st.sidebar.text_area("Paste Node-RED flow JSON (array of nodes)")
    if pasted.strip():
        try:
            raw = json.loads(pasted)
            process_graph = to_process_graph(raw, format="node_red")
        except Exception as e:
            process_error = str(e)

if process_error:
    st.sidebar.error(process_error)
if process_graph is not None:
    st.sidebar.success(f"Loaded: {len(process_graph.units)} units, {len(process_graph.connections)} connections")
    if process_path_used:
        st.sidebar.caption(process_path_used)

# Tabs: Training config | Run / Test | Assistant
tab_config, tab_run, tab_assistant = st.tabs(["Training config", "Run / Test", "Assistant"])

with tab_config:
    st.header("Training config")
    config_source = st.radio("Load training config from", ["Example (temperature)", "Upload YAML"], horizontal=True)
    training_config = None
    config_path_used = None

    if config_source == "Example (temperature)":
        example_cfg = REPO_ROOT / "config" / "examples" / "training_config.yaml"
        if example_cfg.exists():
            try:
                training_config = load_training_config_from_file(example_cfg)
                config_path_used = str(example_cfg)
            except Exception as e:
                st.error(str(e))
    else:
        uploaded_cfg = st.file_uploader("Training config YAML", type=["yaml", "yml"], key="config_upload")
        if uploaded_cfg:
            try:
                raw = yaml.safe_load(uploaded_cfg)
                training_config = to_training_config(raw, format="dict")
                config_path_used = "(uploaded)"
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
    # Fallback: load example training config if not yet loaded
    _training_config = training_config
    if _training_config is None:
        try:
            _training_config = load_training_config_from_file(REPO_ROOT / "config" / "examples" / "training_config.yaml")
        except Exception:
            pass
    if process_graph is None:
        st.warning("Load a process graph first (sidebar).")
    elif _training_config is None:
        st.warning("Load a training config in the Training config tab first.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Run training")
            config_file = st.text_input("Training config path", value=str(REPO_ROOT / "config" / "examples" / "training_config.yaml"), key="train_config_path")
            process_config_file = st.text_input("Process config path (optional)", value=str(REPO_ROOT / "config" / "examples" / "temperature_process.yaml"), key="train_process_path")
            timesteps_override = st.number_input("Timesteps (override)", value=0, min_value=0, step=10000, help="0 = use config value")
            if st.button("Run training"):
                cmd = [sys.executable, str(REPO_ROOT / "train.py"), "--config", config_file]
                if process_config_file and Path(process_config_file).exists():
                    cmd += ["--process-config", process_config_file]
                if timesteps_override > 0:
                    cmd += ["--timesteps", str(timesteps_override)]
                st.code(" ".join(cmd))
                with st.spinner("Training..."):
                    out = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=3600)
                if out.returncode == 0:
                    st.success("Training finished.")
                    if out.stdout:
                        st.text_area("Stdout", out.stdout, height=200)
                else:
                    st.error("Training failed.")
                    if out.stderr:
                        st.text_area("Stderr", out.stderr, height=200)
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
    st.caption("Apply Process Assistant (graph edit) or Training Assistant (config edit) JSON; result is normalized to canonical.")
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
                        from assistants import process_assistant_apply
                        result = process_assistant_apply(process_graph, edit)
                        st.success(f"Result: {len(result.units)} units, {len(result.connections)} connections")
                        st.json(result.model_dump(by_alias=True))
                else:
                    _cfg = training_config or load_training_config_from_file(REPO_ROOT / "config" / "examples" / "training_config.yaml")
                    from assistants import training_assistant_apply
                    result = training_assistant_apply(_cfg, edit)
                    st.success("Config updated")
                    st.json(result.model_dump())
            except Exception as e:
                st.error(str(e))

# Footer: show process graph summary if loaded
if process_graph is not None:
    st.sidebar.divider()
    st.sidebar.subheader("Units")
    for u in process_graph.units:
        st.sidebar.caption(f"{u.id}: {u.type}" + (" (controllable)" if u.controllable else ""))
