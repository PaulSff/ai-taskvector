#!/usr/bin/env python3
"""
Verify Python files parse (no SyntaxError).

  Full repo (CI / local):  python scripts/check_python_syntax.py
  Only some paths:         python scripts/check_python_syntax.py units/foo.py runtime/

Pre-commit runs this on staged *.py files only (see .pre-commit-config.yaml).

Install git hooks (optional):
  pip install pre-commit && pre-commit install
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Skip these path segments anywhere under root
_SKIP_DIR_NAMES = frozenset({
    ".git",
    ".venv",
    "venv",
    "env",
    "ENV",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    "htmlcov",
})


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _should_skip(path: Path) -> bool:
    if any(part in _SKIP_DIR_NAMES for part in path.parts):
        return True
    # Deploy snippets are fragments (e.g. return outside function), not full modules.
    parts = path.parts
    for i in range(len(parts) - 1):
        if parts[i] == "deploy" and parts[i + 1] == "templates":
            return True
    return False


def iter_py_under(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if _should_skip(p):
            continue
        out.append(p)
    return sorted(out)


def _gather_paths(root: Path, explicit: list[Path]) -> list[Path]:
    if not explicit:
        return iter_py_under(root)
    out: list[Path] = []
    for item in explicit:
        p = item if item.is_absolute() else (root / item)
        p = p.resolve()
        if not p.exists():
            print(f"Missing path: {p}", file=sys.stderr)
            continue
        if p.is_file() and p.suffix == ".py":
            if not _should_skip(p):
                out.append(p)
        elif p.is_dir():
            out.extend(iter_py_under(p))
        else:
            print(f"Not a Python file or directory: {p}", file=sys.stderr)
    return sorted(set(out))


def _check_file(path: Path) -> str | None:
    try:
        src = path.read_text(encoding="utf-8")
    except OSError as e:
        return f"{path}: read error: {e}"
    try:
        compile(src, str(path), "exec")
    except SyntaxError as e:
        off = e.offset or 0
        return f"{path}:{e.lineno}:{off}: SyntaxError: {e.msg}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail if any .py file has a SyntaxError.")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root for full scan (default: parent of scripts/).",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to check; if omitted, scan whole repo under --root.",
    )
    args = parser.parse_args(argv)
    root = (args.root or _repo_root()).resolve()
    paths = _gather_paths(root, list(args.paths))
    err_lines: list[str] = []
    for path in paths:
        msg = _check_file(path)
        if msg:
            err_lines.append(msg)
    for line in err_lines:
        print(line, file=sys.stderr)
    if err_lines:
        print(f"\n{len(err_lines)} file(s) with syntax errors.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
