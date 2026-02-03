#!/usr/bin/env python3
"""
Deploy a trained RL agent into a Node-RED or EdgeLinkd flow.

Loads flow JSON, injects the RL Agent node (with model path and wires to
observation sources and action targets), and saves the modified flow.

Usage:
  python scripts/deploy_agent.py --flow flow.json --agent-id temperature_controller \\
    --model models/temperature-control-agent/best/best_model.zip \\
    --obs sensor_1,sensor_2 --actions valve_1,valve_2 [--output flow_with_agent.json]
"""
from pathlib import Path
import argparse
import json
import sys

# Allow running from repo root or from scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deploy.flow_inject import inject_agent_into_flow


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Inject an RL Agent node into a Node-RED/EdgeLinkd flow and save the result."
    )
    ap.add_argument(
        "--flow",
        type=Path,
        required=True,
        help="Path to the flow JSON file (Node-RED or EdgeLinkd format).",
    )
    ap.add_argument(
        "--agent-id",
        type=str,
        required=True,
        help="Unique id for the agent node (e.g. temperature_controller).",
    )
    ap.add_argument(
        "--model",
        type=str,
        required=True,
        help="Path to the trained model (e.g. models/temperature-control-agent/best/best_model.zip).",
    )
    ap.add_argument(
        "--obs",
        type=str,
        required=True,
        help="Comma-separated node ids that send observations into the agent.",
    )
    ap.add_argument(
        "--actions",
        type=str,
        required=True,
        help="Comma-separated node ids that receive actions from the agent.",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for the modified flow. Default: stdout.",
    )
    ap.add_argument(
        "--agent-type",
        type=str,
        default="RLAgent",
        help="Unit type for the agent node (default: RLAgent).",
    )
    args = ap.parse_args()

    flow_path = args.flow
    if not flow_path.is_file():
        print(f"Error: Flow file not found: {flow_path}", file=sys.stderr)
        sys.exit(1)

    with open(flow_path, encoding="utf-8") as f:
        flow = json.load(f)

    observation_source_ids = [s.strip() for s in args.obs.split(",") if s.strip()]
    action_target_ids = [s.strip() for s in args.actions.split(",") if s.strip()]
    if not observation_source_ids or not action_target_ids:
        print("Error: --obs and --actions must each list at least one node id.", file=sys.stderr)
        sys.exit(1)

    try:
        result = inject_agent_into_flow(
            flow,
            agent_id=args.agent_id,
            model_path=args.model,
            observation_source_ids=observation_source_ids,
            action_target_ids=action_target_ids,
            agent_type=args.agent_type,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = args.output
    if out_path is None:
        json.dump(result, sys.stdout, indent=2)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"Deployed flow written to {out_path}")


if __name__ == "__main__":
    main()
