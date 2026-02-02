"""
CLI: apply Process or Training Assistant edit to current graph/config → output canonical.
Usage:
  python -m assistants apply_graph --graph config/examples/temperature_process.yaml --edit edit.json [--out path]
  python -m assistants apply_config --config config/examples/training_config.yaml --edit edit.json [--out path]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml


def _load_json(path: Path) -> dict:
    text = path.read_text()
    return json.loads(text)


def _load_yaml(path: Path) -> dict:
    text = path.read_text()
    return yaml.safe_load(text) or {}


def cmd_apply_graph(args: argparse.Namespace) -> None:
    from normalizer import load_process_graph_from_file
    from assistants.process_assistant import process_assistant_apply

    graph_path = Path(args.graph)
    edit_path = Path(args.edit)
    if not graph_path.exists():
        print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
        sys.exit(1)
    if not edit_path.exists():
        print(f"Error: edit file not found: {edit_path}", file=sys.stderr)
        sys.exit(1)

    current = load_process_graph_from_file(graph_path)
    edit = _load_json(edit_path)
    result = process_assistant_apply(current, edit)

    out_path = Path(args.out) if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            yaml.dump(result.model_dump(by_alias=True), f, default_flow_style=False, sort_keys=False)
        print(f"Updated graph written to {out_path}")
    else:
        yaml.dump(result.model_dump(by_alias=True), sys.stdout, default_flow_style=False, sort_keys=False)


def cmd_apply_config(args: argparse.Namespace) -> None:
    from normalizer import load_training_config_from_file
    from assistants.training_assistant import training_assistant_apply

    config_path = Path(args.config)
    edit_path = Path(args.edit)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    if not edit_path.exists():
        print(f"Error: edit file not found: {edit_path}", file=sys.stderr)
        sys.exit(1)

    current = load_training_config_from_file(config_path)
    edit = _load_json(edit_path)
    result = training_assistant_apply(current, edit)

    out_path = Path(args.out) if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            yaml.dump(result.model_dump(), f, default_flow_style=False, sort_keys=False)
        print(f"Updated config written to {out_path}")
    else:
        yaml.dump(result.model_dump(), sys.stdout, default_flow_style=False, sort_keys=False)


def cmd_text_to_reward(args: argparse.Namespace) -> None:
    from normalizer import load_training_config_from_file
    from assistants.text_to_reward import text_to_reward_apply

    text = (args.text or "").strip()
    if args.stdin and not text:
        text = sys.stdin.read().strip()
    if not text:
        print("Error: provide --text or pipe description via stdin (e.g. echo 'Penalize dumping more' | python -m assistants text_to_reward --stdin)", file=sys.stderr)
        sys.exit(1)

    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
        current = load_training_config_from_file(config_path)
    else:
        from schemas.training_config import TrainingConfig
        current = TrainingConfig()

    try:
        result = text_to_reward_apply(text, current, model=args.model)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Install ollama and start the service: pip install ollama; ollama pull llama3.2", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: could not parse LLM response as reward edit: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out) if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            yaml.dump(result.model_dump(), f, default_flow_style=False, sort_keys=False)
        print(f"Updated config written to {out_path}")
    else:
        yaml.dump(result.model_dump(), sys.stdout, default_flow_style=False, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply assistant edits → normalizer → canonical output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_graph = sub.add_parser("apply_graph", help="Apply Process Assistant graph edit")
    p_graph.add_argument("--graph", required=True, help="Path to current process graph YAML")
    p_graph.add_argument("--edit", required=True, help="Path to edit JSON (from Process Assistant)")
    p_graph.add_argument("--out", default=None, help="Output path for updated graph YAML (default: stdout)")
    p_graph.set_defaults(func=cmd_apply_graph)

    p_config = sub.add_parser("apply_config", help="Apply Training Assistant config edit")
    p_config.add_argument("--config", required=True, help="Path to current training config YAML")
    p_config.add_argument("--edit", required=True, help="Path to edit JSON (from Training Assistant)")
    p_config.add_argument("--out", default=None, help="Output path for updated config YAML (default: stdout)")
    p_config.set_defaults(func=cmd_apply_config)

    p_t2r = sub.add_parser("text_to_reward", help="Text-to-reward: natural language → reward edit via Ollama → merge into config")
    p_t2r.add_argument("--text", default=None, help="Reward description (e.g. 'Penalize dumping more')")
    p_t2r.add_argument("--stdin", action="store_true", help="Read reward description from stdin")
    p_t2r.add_argument("--config", default=None, help="Path to current training config YAML (optional; default empty config)")
    p_t2r.add_argument("--model", default="llama3.2", help="Ollama model name (default: llama3.2)")
    p_t2r.add_argument("--out", default=None, help="Output path for updated config YAML (default: stdout)")
    p_t2r.set_defaults(func=cmd_text_to_reward)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
