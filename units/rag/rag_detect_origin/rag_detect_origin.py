from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Tuple

from rag.content_types.registry import classify_content
from units.registry import UnitSpec, register_unit

# Optional YAML support
try:
    import yaml  # PyYAML
except Exception:
    yaml = None  # type: ignore

RAG_DETECT_ORIGIN_INPUT_PORTS = [("graph", "Any"), ("path", "Any")]
RAG_DETECT_ORIGIN_OUTPUT_PORTS = [
    ("origin", "str"),
    ("graph", "Any"),
    ("error", "str"),
    ("context", "Any"),
]


def _bundle_parts(graph: Any) -> tuple[Any | None, str, bool]:
    """Indexer-style ``{parsed, file_path}``: returns (parsed value, file_path, True) if key ``parsed`` exists."""
    if not isinstance(graph, dict):
        return None, "", False
    if "parsed" not in graph:
        return None, "", False
    fp = str(graph.get("file_path") or "").strip()
    return graph.get("parsed"), fp, True


def _try_parse_text(text: str) -> Tuple[Optional[object], Optional[str]]:
    """
    Try parsing text into a JSON/YAML Python object.
    Returns (parsed_obj or None, error_message or None).

    Strategy:
      - Try JSON first (backward compatible).
      - On JSON decode failure, try YAML.safe_load if available.
      - If YAML parses to a scalar (non-dict/list), wrap as {"value": scalar}.
      - If YAML unavailable when needed, return an explanatory error.
    """
    s = text or ""
    s_stripped = s.strip()
    if not s_stripped:
        return None, "empty text"

    # Try JSON first
    try:
        parsed = json.loads(s)
        return parsed, None
    except json.JSONDecodeError as je:
        # JSON failed; try YAML if available
        if yaml is None:
            return (
                None,
                f"JSON decode error: {je}. PyYAML not installed to try YAML fallback.",
            )
        try:
            parsed_yaml = yaml.safe_load(s)
            # Accept dict/list; wrap scalars into {"value": ...}
            if isinstance(parsed_yaml, (dict, list)):
                return parsed_yaml, None
            return {"value": parsed_yaml}, None
        except Exception as ye:
            return None, f"JSON decode error: {je}; YAML parse error: {ye}"


def _read_file_text(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Read file as text (utf-8, replace errors). Returns (text or None, error or None)."""
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
        return txt, None
    except Exception as e:
        return None, str(e)


def _graph_to_data(graph: Any) -> tuple[dict | list | None, Path]:
    """Return (JSON/YAML root for classify, path hint for discriminants)."""
    if graph is None:
        return None, Path(".")

    b_parsed, b_fp, is_bundle = _bundle_parts(graph)
    if is_bundle:
        hint = Path(b_fp) if b_fp else Path(".")
        # If parsed is already a dict/list, return it
        if isinstance(b_parsed, (dict, list)):
            return b_parsed, hint

        # If parsed is None but file path exists, try loading from file
        if b_parsed is None and b_fp:
            pth = Path(b_fp)
            suffix = pth.suffix.lower()
            if suffix in (".json", ".yaml", ".yml") and pth.is_file():
                txt, err = _read_file_text(pth)
                if txt is None:
                    return None, pth
                parsed, perr = _try_parse_text(txt)
                if parsed is None:
                    return None, pth
                if not isinstance(parsed, (dict, list)):
                    parsed = {"value": parsed}
                return parsed, pth

        # If parsed is a string: try parsing as inline JSON/YAML
        if isinstance(b_parsed, str):
            s = b_parsed.strip()
            if not s:
                return None, hint
            parsed, perr = _try_parse_text(s)
            if parsed is None:
                return None, hint
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, hint

        return None, hint

    # Not a bundle
    if isinstance(graph, (dict, list)):
        return graph, Path(".")

    if isinstance(graph, str):
        s = graph.strip()
        if not s:
            return None, Path(".")
        pth = Path(s)
        suffix = pth.suffix.lower()

        # If path-like and exists as file with recognized extension, read and parse
        if suffix in (".json", ".yaml", ".yml") and pth.is_file():
            txt, err = _read_file_text(pth)
            if txt is None:
                return None, pth
            parsed, perr = _try_parse_text(txt)
            if parsed is None:
                return None, pth
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, pth

        # If it *looks like* JSON inline, try parsing
        if s[:1] in ("{", "["):
            parsed, perr = _try_parse_text(s)
            if parsed is None:
                return None, Path(".")
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, Path(".")

        # If YAML available, try parsing any non-path string as YAML
        if yaml is not None:
            parsed, perr = _try_parse_text(s)
            if parsed is None:
                return None, Path(".")
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, Path(".")

        # Not parseable: keep as path hint (could be .json/.yaml path that doesn't exist yet)
        return None, Path(s)

    # Pydantic or dataclass-like objects
    if hasattr(graph, "model_dump"):
        try:
            dumped = graph.model_dump()
            if isinstance(dumped, (dict, list)):
                return dumped, Path(".")
        except Exception:
            pass

    if hasattr(graph, "dict"):
        try:
            dumped = getattr(graph, "dict")()
            if isinstance(dumped, (dict, list)):
                return dumped, Path(".")
        except Exception:
            pass

    return None, Path(".")


def _rag_detect_origin_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Output 0: origin (content_kind); output 1: normalized graph; output 2: error; output 3: routing context."""
    g_in = inputs.get("graph") if inputs else None
    p_in = inputs.get("path") if inputs else None
    graph_in: Any = None
    if g_in is not None and not (isinstance(g_in, str) and not str(g_in).strip()):
        graph_in = g_in
    elif p_in is not None and not (isinstance(p_in, str) and not str(p_in).strip()):
        graph_in = p_in
    err_msg = ""
    vp = str(params.get("virtual_path") or "").strip()
    disc_path = Path(vp) if vp else Path(".")
    fp_out = ""
    try:
        data, hint = _graph_to_data(graph_in)
        if hint != Path("."):
            disc_path = hint
        if isinstance(graph_in, str) and graph_in.strip():
            fp_out = graph_in.strip()
        elif isinstance(graph_in, dict) and graph_in.get("file_path"):
            fp_out = str(graph_in.get("file_path") or "").strip()

        raw = classify_content(
            disc_path, data
        )  # returns dict with keys: family, content_kind, id
        origin = str(raw.get("content_kind") or raw.get("id") or "") or "json-generic"

    except Exception as e:
        origin = "json-generic"
        err_msg = str(e)
        data = None
    ctx = {"file_path": fp_out, "parsed": data, "origin": origin}
    return (
        {
            "origin": origin,
            "graph": data,
            "error": err_msg,
            "context": ctx,
        },
        state,
    )


def register_rag_detect_origin() -> None:
    """Register the RagDetectOrigin unit type."""
    register_unit(
        UnitSpec(
            type_name="RagDetectOrigin",
            input_ports=RAG_DETECT_ORIGIN_INPUT_PORTS,
            output_ports=RAG_DETECT_ORIGIN_OUTPUT_PORTS,
            step_fn=_rag_detect_origin_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Detect content_kind; supports path / JSON/YAML string / bundle {parsed,file_path}. Outputs origin, graph, error, context.",
        )
    )


__all__ = [
    "register_rag_detect_origin",
    "RAG_DETECT_ORIGIN_INPUT_PORTS",
    "RAG_DETECT_ORIGIN_OUTPUT_PORTS",
    "yaml",
    "classify_content",
]
