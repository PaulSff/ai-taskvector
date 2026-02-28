"""
Unit documentation / UnitSpec embedder for external runtimes (Node-RED, n8n, etc.).

Responsibilities:
- Given a unit name + backend + node_type and a mydata folder:
  - Locate the unit's source folder (JS/TS/HTML/etc.).
  - If docs already exist (UnitSpec JSON + API markdown), skip.
  - Otherwise call an LLM with UNIT_DOC_SYSTEM prompt and the source files.
  - Write:
      mydata/{nodename}UnitSpec.json
      mydata/{nodename}_API.md
  - Optionally trigger a RAG update so these docs become searchable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from assistants.prompts import UNIT_DOC_SYSTEM

try:
    # Optional dependency; we only import when actually calling the LLM
    from LLM_integrations.ollama import chat_completion as _ollama_chat
except Exception:  # pragma: no cover - handled at call time
    _ollama_chat = None  # type: ignore[assignment]


@dataclass
class UnitIdentity:
    """Logical identity of a unit (used to drive doc generation)."""

    nodename: str
    backend: str  # e.g. "node-red", "n8n", "pyflow", "canonical", "comfy", "other"
    node_type: str | None = None  # backend-specific node type string


def _candidate_source_dirs(identity: UnitIdentity, mydata_dir: Path) -> list[Path]:
    """
    Return candidate source directories for this unit.

    Heuristics (minimal for now, can be extended later):
    - Node-RED: mydata/node-red/nodes/{nodename}/
    - n8n:      mydata/n8n/nodes/{nodename}/
    """
    nodename = identity.nodename
    root = mydata_dir.resolve()
    out: list[Path] = []

    if identity.backend.lower() == "node-red":
        p = root / "node-red" / "nodes" / nodename
        if p.is_dir():
            out.append(p)
    if identity.backend.lower() == "n8n":
        p = root / "n8n" / "nodes" / nodename
        if p.is_dir():
            out.append(p)
    # Other backends (pyflow, comfy, canonical) can be added later
    return out


def _collect_source_files(folder: Path) -> list[tuple[str, str]]:
    """
    Collect relevant source files under folder.

    Returns list of (relative_path, text_content).
    """
    exts = {".js", ".ts", ".tsx", ".jsx", ".html", ".json", ".py"}
    out: list[tuple[str, str]] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            rel = str(p.relative_to(folder))
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append((rel, text))
    return out


def _build_llm_user_prompt(identity: UnitIdentity, files: Iterable[tuple[str, str]]) -> str:
    """
    Build the user message content for UNIT_DOC_SYSTEM.

    We keep it plain-text but structured enough for the LLM to parse.
    """
    lines: list[str] = []
    lines.append(f"nodename: {identity.nodename}")
    lines.append(f"backend: {identity.backend}")
    if identity.node_type:
        lines.append(f"node_type: {identity.node_type}")
    lines.append("")
    lines.append("Source files for this unit:")
    for rel, text in files:
        lines.append("")
        lines.append(f"=== FILE: {rel} ===")
        lines.append(text)
    return "\n".join(lines)


def _call_unit_doc_llm(
    identity: UnitIdentity,
    files: list[tuple[str, str]],
    *,
    host: str,
    model: str,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """Call Ollama (or configured LLM) with UNIT_DOC_SYSTEM and return parsed JSON."""
    if _ollama_chat is None:
        raise RuntimeError(
            "Unit doc generation requires ollama (LLM_integrations.ollama). "
            "Install with: pip install ollama; ensure Ollama is running."
        )

    user_content = _build_llm_user_prompt(identity, files)
    messages = [
        {"role": "system", "content": UNIT_DOC_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    raw = _ollama_chat(host=host, model=model, messages=messages, timeout_s=timeout_s)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:  # pragma: no cover - depends on model behavior
        raise ValueError(f"Unit doc LLM response is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Unit doc LLM response must be a JSON object")
    if "unit_spec" not in data or "api_markdown" not in data:
        raise ValueError("Unit doc LLM response must contain 'unit_spec' and 'api_markdown' keys")
    return data


def _target_paths(mydata_dir: Path, identity: UnitIdentity) -> tuple[Path, Path]:
    """Return (spec_path, api_md_path) for this unit."""
    root = mydata_dir.resolve()
    spec = root / f"{identity.nodename}UnitSpec.json"
    api = root / f"{identity.nodename}_API.md"
    return spec, api


def ensure_unit_docs_for_unit(
    identity: UnitIdentity,
    mydata_dir: Path,
    *,
    llm_host: str,
    llm_model: str,
    timeout_s: int = 120,
    force: bool = False,
) -> bool:
    """
    Ensure UnitSpec + API docs exist for a single unit.

    Returns True if docs were created/updated, False if skipped (already present or no sources).
    """
    spec_path, api_path = _target_paths(mydata_dir, identity)
    if not force and spec_path.is_file() and api_path.is_file():
        return False

    candidates = _candidate_source_dirs(identity, mydata_dir)
    if not candidates:
        return False

    # For now, use the first matching folder
    folder = candidates[0]
    files = _collect_source_files(folder)
    if not files:
        return False

    result = _call_unit_doc_llm(
        identity,
        files,
        host=llm_host,
        model=llm_model,
        timeout_s=timeout_s,
    )
    unit_spec = result.get("unit_spec")
    api_markdown = result.get("api_markdown", "")

    spec_path.write_text(json.dumps(unit_spec, ensure_ascii=False, indent=2), encoding="utf-8")
    api_path.write_text(str(api_markdown), encoding="utf-8")
    return True


def ensure_unit_docs_for_units(
    identities: list[UnitIdentity],
    mydata_dir: Path,
    *,
    llm_host: str,
    llm_model: str,
    timeout_s: int = 120,
    force: bool = False,
) -> int:
    """
    Ensure UnitSpec + API docs exist for multiple units.

    Returns number of units for which docs were created/updated.
    """
    count = 0
    for ident in identities:
        if ensure_unit_docs_for_unit(
            ident,
            mydata_dir,
            llm_host=llm_host,
            llm_model=llm_model,
            timeout_s=timeout_s,
            force=force,
        ):
            count += 1
    return count

