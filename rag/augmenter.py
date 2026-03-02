"""
Unit documentation augmenter for external runtimes and repo (canonical) units.

Augments the RAG corpus by generating unit docs (UnitSpec + API markdown) from source
and writing them under mydata; the RAG indexer then embeds and indexes those files.

Responsibilities:
- Given a unit name + backend + node_type and a mydata folder:
  - Locate the unit's source folder (JS/TS/HTML for node-red/n8n; Python under units/ for canonical).
  - If docs already exist, skip (both spec+API for external; API only for canonical).
  - Call an LLM and write:
      External (node-red, n8n): mydata/{nodename}UnitSpec.json + mydata/{nodename}_API.md
      Canonical (repo units):  mydata/{nodename}_API.md only (UnitSpec is from the registry).

Nodename / folder resolution:
- UnitIdentity may have path_hint (e.g. "hardware/Arduino") from a type→folder map.
- Map: built-in TYPE_TO_FOLDER_MAP plus optional mydata/node-red/unit_type_to_folder.json.
- Fallback: nodes/{nodename}; then discovery: dirs under nodes/ with a .js file matching nodename.
- Canonical: discover by scanning units/ for .py files that register UnitSpec(type_name="...").
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from assistants.prompts import UNIT_DOC_API_ONLY_SYSTEM, UNIT_DOC_SYSTEM

try:
    # Optional dependency; we only import when actually calling the LLM
    from LLM_integrations.ollama import chat_completion as _ollama_chat
except Exception:  # pragma: no cover - handled at call time
    _ollama_chat = None  # type: ignore[assignment]


# Optional mapping file under mydata (JSON: {"unit type": "path/under/nodes"})
UNIT_TYPE_TO_FOLDER_FILENAME = "unit_type_to_folder.json"

# Built-in type → folder path under nodes/ (extend via file or override)
TYPE_TO_FOLDER_MAP: dict[str, str] = {
    "arduino in": "hardware/Arduino",
    "arduino out": "hardware/Arduino",
}


def _load_type_to_folder_map(mydata_dir: Path | None) -> dict[str, str]:
    """Merge built-in map with optional mydata/node-red/unit_type_to_folder.json."""
    out = dict(TYPE_TO_FOLDER_MAP)
    if not mydata_dir or not mydata_dir.is_dir():
        return out
    for base in (mydata_dir / "node-red", mydata_dir):
        path = base / UNIT_TYPE_TO_FOLDER_FILENAME
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(k, str) and isinstance(v, str):
                            out[k.strip()] = v.strip().replace("\\", "/").strip("/")
            except (OSError, json.JSONDecodeError):
                pass
    return out


@dataclass
class UnitIdentity:
    """Logical identity of a unit (used to drive doc generation)."""

    nodename: str
    backend: str  # e.g. "node-red", "n8n", "pyflow", "canonical", "comfy", "other"
    node_type: str | None = None  # backend-specific node type string
    path_hint: str | None = None  # relative path under nodes/ (e.g. "hardware/Arduino")


def _nodename_from_unit_type(unit_type: str) -> str:
    """Derive a folder-friendly nodename from unit type (e.g. 'arduino in' -> 'arduino_in')."""
    if not unit_type or not isinstance(unit_type, str):
        return "unknown"
    return unit_type.strip().lower().replace(" ", "_")


def graph_to_unit_identities(
    graph: Any,
    *,
    mydata_dir: Path | None = None,
) -> list[UnitIdentity]:
    """
    Build a list of UnitIdentity from an applied process graph (e.g. after import_workflow).

    graph: ProcessGraph or dict with "units" and "origin".
    mydata_dir: optional; if provided, used to load unit_type_to_folder map and set path_hint.
    Returns deduplicated list by (nodename, backend).
    """
    # Normalize to dict with units + origin
    if hasattr(graph, "model_dump"):
        g = graph.model_dump(by_alias=True)
    elif isinstance(graph, dict):
        g = graph
    else:
        return []

    units = g.get("units") or []
    origin = g.get("origin")
    # Backend is per-graph; explicit rules only (no fallback).
    # - origin.canonical truthy -> canonical.
    # - origin.node_red truthy -> node-red.
    # - origin.n8n truthy -> n8n.
    # If origin is None or none of these are set, we do not produce identities.
    backend: str | None = None
    if origin is not None:
        if isinstance(origin, dict):
            if origin.get("canonical"):
                backend = "canonical"
            elif origin.get("n8n"):
                backend = "n8n"
            elif origin.get("node_red"):
                backend = "node-red"
        else:
            if getattr(origin, "canonical", None):
                backend = "canonical"
            elif getattr(origin, "n8n", None):
                backend = "n8n"
            elif getattr(origin, "node_red", None):
                backend = "node-red"
    if backend is None:
        return []

    type_to_folder = _load_type_to_folder_map(mydata_dir) if mydata_dir else TYPE_TO_FOLDER_MAP
    seen: set[tuple[str, str]] = set()
    out: list[UnitIdentity] = []
    for u in units:
        if not isinstance(u, dict):
            continue
        utype = (u.get("type") or "").strip() or (u.get("id") or "unknown")
        nodename = _nodename_from_unit_type(utype)
        key = (nodename, backend)
        if key in seen:
            continue
        seen.add(key)
        path_hint = type_to_folder.get(utype) or type_to_folder.get(utype.lower())
        out.append(
            UnitIdentity(
                nodename=nodename,
                backend=backend,
                node_type=utype or None,
                path_hint=path_hint,
            )
        )
    return out


def identities_for_unit_ids(
    graph: Any,
    unit_ids: list[str],
    *,
    mydata_dir: Path | None = None,
) -> list[UnitIdentity]:
    """
    Return UnitIdentity list for only the units whose id is in unit_ids.
    Used for targeted augmentation when the assistant requests specs for specific units.
    Deduplicated by (nodename, backend) so each type is augmented at most once.
    """
    all_identities = graph_to_unit_identities(graph, mydata_dir=mydata_dir)
    if not all_identities or not unit_ids:
        return []
    want = {str(uid).strip() for uid in unit_ids if uid}
    if not want:
        return []
    # Build unit id -> unit type from graph
    if hasattr(graph, "model_dump"):
        g = graph.model_dump(by_alias=True)
    else:
        g = graph if isinstance(graph, dict) else {}
    units = g.get("units") or []
    id_to_type: dict[str, str] = {}
    for u in units:
        if not isinstance(u, dict):
            continue
        uid = u.get("id")
        utype = (u.get("type") or "").strip() or (u.get("id") or "unknown")
        if uid:
            id_to_type[str(uid)] = utype
    seen: set[tuple[str, str]] = set()
    out: list[UnitIdentity] = []
    for uid in unit_ids:
        if not uid or str(uid).strip() not in want:
            continue
        utype = id_to_type.get(str(uid))
        if not utype:
            continue
        nodename = _nodename_from_unit_type(utype)
        for i in all_identities:
            if i.nodename == nodename:
                key = (i.nodename, i.backend)
                if key not in seen:
                    seen.add(key)
                    out.append(i)
                break
    return out


def _discover_canonical_type_to_dir(units_dir: Path) -> dict[str, Path]:
    """
    Scan units_dir for .py files that register a unit (UnitSpec(type_name="...")).
    Returns dict mapping type_name -> directory containing that .py (the unit folder).
    """
    out: dict[str, Path] = {}
    if not units_dir.is_dir():
        return out
    # Match type_name="Valve" or type_name='Valve' inside register_unit(UnitSpec(...))
    pattern = re.compile(r"type_name\s*=\s*[\"']([^\"']+)[\"']")
    try:
        for py_path in units_dir.rglob("*.py"):
            if not py_path.is_file():
                continue
            try:
                text = py_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "register_unit" not in text or "UnitSpec" not in text:
                continue
            for m in pattern.finditer(text):
                type_name = m.group(1).strip()
                if type_name:
                    # Use the directory containing this .py as the unit folder
                    out[type_name] = py_path.parent
    except OSError:
        pass
    return out


def _discover_source_dirs_by_js(
    nodes_root: Path,
    nodename: str,
    *,
    max_candidates: int = 3,
) -> list[Path]:
    """
    Find directories under nodes_root that contain a .js file whose stem matches nodename.
    Slug = first segment of nodename (e.g. "arduino_in" -> "arduino"); match is case-insensitive.
    """
    slug = (nodename.split("_")[0] if nodename else "").lower()
    if not slug or not nodes_root.is_dir():
        return []
    out: list[Path] = []
    seen: set[Path] = set()
    try:
        for d in sorted(nodes_root.rglob("*")):
            if not d.is_dir() or d in seen:
                continue
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() == ".js" and slug in f.stem.lower():
                    if d not in seen:
                        seen.add(d)
                        out.append(d)
                        if len(out) >= max_candidates:
                            return out
                    break
    except OSError:
        pass
    return out


def _candidate_source_dirs(
    identity: UnitIdentity,
    mydata_dir: Path,
    *,
    units_dir: Path | None = None,
    canonical_type_to_dir: dict[str, Path] | None = None,
) -> list[Path]:
    """
    Return candidate source directories for this unit.

    For canonical backend: use canonical_type_to_dir (from _discover_canonical_type_to_dir(units_dir)).
    For node-red/n8n: (1) path_hint, (2) nodes/{nodename}, (3) discovery by .js match.
    """
    nodename = identity.nodename
    root = mydata_dir.resolve()
    out: list[Path] = []

    if identity.backend.lower() == "canonical":
        if canonical_type_to_dir is not None:
            type_key = (identity.node_type or nodename).strip()
            if type_key:
                folder = canonical_type_to_dir.get(type_key)
                if folder is not None and folder.is_dir():
                    out.append(folder.resolve())
        return out

    def _safe_under(base: Path, p: Path) -> bool:
        try:
            p.resolve().relative_to(base.resolve())
            return True
        except ValueError:
            return False

    if identity.backend.lower() == "node-red":
        nodes_base = root / "node-red" / "nodes"
        if identity.path_hint:
            p = (nodes_base / identity.path_hint).resolve()
            if p.is_dir() and _safe_under(nodes_base, p):
                out.append(p)
        if not out:
            p = nodes_base / nodename
            if p.is_dir():
                out.append(p)
        if not out and nodes_base.is_dir():
            out.extend(_discover_source_dirs_by_js(nodes_base, nodename))
    elif identity.backend.lower() == "n8n":
        nodes_base = root / "n8n" / "nodes"
        if identity.path_hint:
            p = (nodes_base / identity.path_hint).resolve()
            if p.is_dir() and _safe_under(nodes_base, p):
                out.append(p)
        if not out:
            p = nodes_base / nodename
            if p.is_dir():
                out.append(p)
        if not out and nodes_base.is_dir():
            out.extend(_discover_source_dirs_by_js(nodes_base, nodename))
    return out


def _collect_source_files(folder: Path) -> list[tuple[str, str]]:
    """
    Collect relevant source files under folder.

    Includes code (.py, .js, etc.) and README.md / other .md for API doc context.
    Returns list of (relative_path, text_content).
    """
    exts = {".js", ".ts", ".tsx", ".jsx", ".html", ".json", ".py", ".md"}
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


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Serialize a UnitSpec (from registry) to a JSON-suitable dict for the API-only prompt."""
    return {
        "type_name": getattr(spec, "type_name", ""),
        "input_ports": [
            {"name": p[0], "dtype": p[1] if len(p) > 1 else "any"}
            for p in (getattr(spec, "input_ports", None) or [])
        ],
        "output_ports": [
            {"name": p[0], "dtype": p[1] if len(p) > 1 else "any"}
            for p in (getattr(spec, "output_ports", None) or [])
        ],
        "controllable": getattr(spec, "controllable", False),
    }


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
    rag_context: str | None = None,
) -> dict[str, Any]:
    """Call Ollama (or configured LLM) with UNIT_DOC_SYSTEM and return parsed JSON."""
    if _ollama_chat is None:
        raise RuntimeError(
            "Unit doc generation requires ollama (LLM_integrations.ollama). "
            "Install with: pip install ollama; ensure Ollama is running."
        )

    system_content = UNIT_DOC_SYSTEM
    if rag_context and rag_context.strip():
        system_content = system_content + "\n\n---\nRelevant context from knowledge base (use for conventions and patterns):\n" + rag_context.strip()
    user_content = _build_llm_user_prompt(identity, files)
    messages = [
        {"role": "system", "content": system_content},
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


def _build_llm_user_prompt_api_only(
    spec_dict: dict[str, Any],
    files: Iterable[tuple[str, str]],
) -> str:
    """Build user message for UNIT_DOC_API_ONLY_SYSTEM: existing UnitSpec + source files."""
    lines: list[str] = []
    lines.append("Existing UnitSpec (from registry):")
    lines.append(json.dumps(spec_dict, indent=2))
    lines.append("")
    lines.append("Source files for this unit:")
    for rel, text in files:
        lines.append("")
        lines.append(f"=== FILE: {rel} ===")
        lines.append(text)
    return "\n".join(lines)


def _call_unit_doc_llm_api_only(
    identity: UnitIdentity,
    spec_dict: dict[str, Any],
    files: list[tuple[str, str]],
    *,
    host: str,
    model: str,
    timeout_s: int = 120,
    rag_context: str | None = None,
) -> dict[str, Any]:
    """Call LLM with UNIT_DOC_API_ONLY_SYSTEM; return dict with only api_markdown."""
    if _ollama_chat is None:
        raise RuntimeError(
            "Unit doc generation requires ollama (LLM_integrations.ollama). "
            "Install with: pip install ollama; ensure Ollama is running."
        )
    system_content = UNIT_DOC_API_ONLY_SYSTEM
    if rag_context and rag_context.strip():
        system_content = system_content + "\n\n---\nRelevant context from knowledge base (use for conventions and patterns):\n" + rag_context.strip()
    user_content = _build_llm_user_prompt_api_only(spec_dict, files)
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    raw = _ollama_chat(host=host, model=model, messages=messages, timeout_s=timeout_s)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Unit doc API-only LLM response is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Unit doc API-only LLM response must be a JSON object")
    if "api_markdown" not in data:
        raise ValueError("Unit doc API-only LLM response must contain 'api_markdown' key")
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
    units_dir: Path | None = None,
    canonical_type_to_dir: dict[str, Path] | None = None,
    rag_context: str | None = None,
) -> bool:
    """
    Ensure UnitSpec + API docs exist for a single unit (or API only for canonical).

    For backend "canonical": UnitSpec is taken from the registry; only API markdown is generated
    and written (no UnitSpec file). Pass units_dir and/or canonical_type_to_dir for source discovery.
    Returns True if docs were created/updated, False if skipped.
    """
    spec_path, api_path = _target_paths(mydata_dir, identity)
    is_canonical = identity.backend.lower() == "canonical"

    if is_canonical:
        if not force and api_path.is_file():
            return False
        if canonical_type_to_dir is None and units_dir is not None:
            canonical_type_to_dir = _discover_canonical_type_to_dir(units_dir)
        candidates = _candidate_source_dirs(
            identity,
            mydata_dir,
            units_dir=units_dir,
            canonical_type_to_dir=canonical_type_to_dir,
        )
        if not candidates:
            return False
        folder = candidates[0]
        files = _collect_source_files(folder)
        if not files:
            return False
        try:
            from units.registry import get_unit_spec
        except ImportError:
            return False
        type_key = (identity.node_type or identity.nodename or "").strip()
        spec = get_unit_spec(type_key)
        if spec is None:
            return False
        spec_dict = _spec_to_dict(spec)
        result = _call_unit_doc_llm_api_only(
            identity,
            spec_dict,
            files,
            host=llm_host,
            model=llm_model,
            timeout_s=timeout_s,
            rag_context=rag_context,
        )
        api_path.write_text(str(result.get("api_markdown", "")), encoding="utf-8")
        return True

    if not force and spec_path.is_file() and api_path.is_file():
        return False
    candidates = _candidate_source_dirs(
        identity,
        mydata_dir,
        canonical_type_to_dir=None,
    )
    if not candidates:
        return False
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
        rag_context=rag_context,
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
    units_dir: Path | None = None,
    rag_context: str | None = None,
) -> int:
    """
    Ensure UnitSpec + API docs exist for multiple units.

    For canonical units, pass units_dir so repo units/ are discovered and only API docs are written.
    If rag_context is provided (e.g. from RAG retrieval), it is injected into the LLM system prompt
    so the model can use n8n/Node-RED conventions and patterns when generating docs.
    Returns number of units for which docs were created/updated.
    """
    canonical_type_to_dir: dict[str, Path] | None = None
    if units_dir is not None and any(i.backend.lower() == "canonical" for i in identities):
        canonical_type_to_dir = _discover_canonical_type_to_dir(units_dir)
    count = 0
    for ident in identities:
        if ensure_unit_docs_for_unit(
            ident,
            mydata_dir,
            llm_host=llm_host,
            llm_model=llm_model,
            timeout_s=timeout_s,
            force=force,
            units_dir=units_dir,
            canonical_type_to_dir=canonical_type_to_dir,
            rag_context=rag_context,
        ):
            count += 1
    return count
