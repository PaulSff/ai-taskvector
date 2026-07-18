#!/usr/bin/env python3
"""
Run: python create_environment.py --root .. --environment "env_name" --readme "Production environment units."
"""
from __future__ import annotations

import argparse
from pathlib import Path


from units.canonical._scaffold_env import run_list_environment


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new environment under units/<env>/.")
    parser.add_argument(
        "--root",
        default=".",
        help="Repo root path (must contain the units/ directory). Default: current directory.",
    )
    parser.add_argument(
        "--environment",
        required=True,
        help='New environment id (e.g. "Prod-Env" -> will normalize to "prod_env").',
    )
    parser.add_argument(
        "--readme",
        default="",
        help="README.md content for the new environment package. Default: empty.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    result = run_list_environment(
        root=root,
        new_environment_id=args.environment,
        readme_md=args.readme,
    )

    # Simple printout
    print(result)
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
