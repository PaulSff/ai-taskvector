from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, TypedDict, TypeGuard, runtime_checkable

from core.schemas.primitives import Data, Output
from rag.content_types.registry import classify_content
from units.registry import UnitSpec, register_unit

# Optional YAML support
try:
    import yaml  # PyYAML
except ImportError:
    yaml = None  # type: ignore


@runtime_checkable
class Dumpable(Protocol):
    def model_dump(self) -> Data | list[object]: ...
    def dict(self) -> Data | list[object]: ...

type GraphInput = str | Data | list[object] | Dumpable

class RoutingContext(TypedDict):
    file_path: str
    parsed: Data | list[object] | None
    origin: str

RAG_DETECT_ORIGIN_INPUT_PORTS = [
    ("graph", "GraphInput"),
    ("path", "str")
]
RAG_DETECT_ORIGIN_OUTPUT_PORTS = [
    ("origin", "str"),
    ("graph", "GraphInput"),
    ("error", "str"),
    ("context", "RoutingContext"),
]

def _is_blank_str(x: object) -> TypeGuard[str]:
    return isinstance(x, str) and not x.strip()

def _is_graph_input(x: object) -> TypeGuard[GraphInput]:
    return isinstance(x, (str, dict, list))

def _bundle_parts(
    graph: GraphInput,
) -> tuple[Data | list[object] | None, str, bool]:
    if not isinstance(graph, dict) or "parsed" not in graph:
        return None, "", False

    parsed = graph["parsed"]
    if parsed is not None and not isinstance(parsed, (dict, list)):
        return None, "", False

    fp = str(graph.get("file_path") or "").strip()
    return parsed, fp, True


def _try_parse_text(text: str) -> tuple[object | None, str | None]:
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
            if isinstance(parsed_yaml, (dict, list)):
                return parsed_yaml, None
            return {"value": parsed_yaml}, None
        except yaml.YAMLError as ye:
            return None, f"YAML parse error: {ye}"
        except TypeError as te:
            return None, f"YAML parse error: {te}"


def _read_file_text(path: Path) -> tuple[str | None, str | None]:
    """Read file as text (utf-8, replace errors). Returns (text or None, error or None)."""
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
        return txt, None
    except OSError as e:
        return None, str(e)


def _graph_to_data(
    graph: GraphInput | None,
) -> tuple[Data | list[object] | None, Path, str | None]:
    """
    Return (JSON/YAML root for classify, path hint for discriminants, error_message).

    error_message is non-None when a file/parse attempt fails; callers should propagate it
    to the unit's error output. When there is no error, error_message is None.
    """
    if graph is None:
        return None, Path("."), None

    b_parsed, b_fp, is_bundle = _bundle_parts(graph)
    if is_bundle:
        hint = Path(b_fp) if b_fp else Path(".")
        # If parsed is already a dict/list, return it
        if isinstance(b_parsed, (dict, list)):
            return b_parsed, hint, None

        # If parsed is None but file path exists, try loading from file
        if b_parsed is None and b_fp:
            pth = Path(b_fp)
            suffix = pth.suffix.lower()
            if suffix in (".json", ".yaml", ".yml") and pth.is_file():
                txt, err = _read_file_text(pth)
                if txt is None:
                    return None, pth, err or "failed to read file"
                parsed, perr = _try_parse_text(txt)
                if parsed is None:
                    return None, pth, perr or "failed to parse file"
                if not isinstance(parsed, (dict, list)):
                    parsed = {"value": parsed}
                return parsed, pth, None

            # File path doesn't exist / unsupported suffix: keep prior behavior (no parse error emitted)
            return None, pth, None

        # If parsed is a string: try parsing as inline JSON/YAML
        if isinstance(b_parsed, str):
            s = b_parsed.strip()
            if not s:
                return None, hint, "empty text"
            parsed, perr = _try_parse_text(s)
            if parsed is None:
                return None, hint, perr or "failed to parse inline JSON/YAML"
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, hint, None

        return None, hint, None

    # Not a bundle
    if isinstance(graph, (dict, list)):
        return graph, Path("."), None

    if isinstance(graph, str):
        s = graph.strip()
        if not s:
            return None, Path("."), None

        pth = Path(s)
        suffix = pth.suffix.lower()

        # If path-like and exists as file with recognized extension, read and parse
        if suffix in (".json", ".yaml", ".yml") and pth.is_file():
            txt, err = _read_file_text(pth)
            if txt is None:
                return None, pth, err or "failed to read file"
            parsed, perr = _try_parse_text(txt)
            if parsed is None:
                return None, pth, perr or "failed to parse file"
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, pth, None

        # If it *looks like* JSON inline, try parsing
        if s[:1] in ("{", "["):
            parsed, perr = _try_parse_text(s)
            if parsed is None:
                return None, Path("."), perr or "failed to parse inline JSON"
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, Path("."), None

        # If YAML available, try parsing any non-path string as YAML
        if yaml is not None:
            parsed, perr = _try_parse_text(s)
            if parsed is None:
                return None, Path("."), perr or "failed to parse inline YAML"
            if not isinstance(parsed, (dict, list)):
                parsed = {"value": parsed}
            return parsed, Path("."), None

        # Not parseable: keep as path hint (could be .json/.yaml path that doesn't exist yet)
        return None, Path(s), None

    # Pydantic or dataclass-like objects
    if hasattr(graph, "model_dump"):
        try:
            dumped = graph.model_dump()
            if isinstance(dumped, (dict, list)):
                return dumped, Path("."), None
        except AttributeError:
            pass  # graph has no model_dump()
        except TypeError:
            pass  # model_dump called/used with incompatible args/return shape

    if hasattr(graph, "dict"):
        try:
            dumped = graph.dict()
            if isinstance(dumped, (dict, list)):
                return dumped, Path("."), None
        except AttributeError:
            pass  # graph has no .dict()
        except TypeError:
            pass  # .dict() called/used in an unexpected way

    return None, Path("."), None


def _rag_detect_origin_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Output 0: origin (content_kind); output 1: normalized graph; output 2: error; output 3: routing context."""
    g_in = inputs.get("graph") if inputs else None
    p_in = inputs.get("path") if inputs else None
    graph_in: GraphInput | None = None

    if g_in is not None and not _is_blank_str(g_in) and _is_graph_input(g_in):
        graph_in = g_in
    elif p_in is not None and not _is_blank_str(p_in) and _is_graph_input(p_in):
        graph_in = p_in

    err_msg = ""
    vp = str(params.get("virtual_path") or "").strip()
    disc_path = Path(vp) if vp else Path(".")
    fp_out = ""

    try:
        data, hint, parse_err = _graph_to_data(graph_in)
        if hint != Path("."):
            disc_path = hint

        # Preserve existing "context/file_path" behavior
        if isinstance(graph_in, str) and graph_in.strip():
            fp_out = graph_in.strip()
        elif isinstance(graph_in, dict) and graph_in.get("file_path"):
            fp_out = str(graph_in.get("file_path") or "").strip()

        if parse_err:
            # Propagate parse/file errors to the unit's error port; keep behavior: graph output is None
            raise ValueError(parse_err)

        raw = classify_content(
            disc_path, data
        )  # returns dict with keys: family, content_kind, id
        origin = str(raw.get("content_kind") or raw.get("id") or "") or "json-generic"

    except (AttributeError, TypeError, ValueError) as e:
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
            environment_tags=["rag"],
            environment_tags_are_agnostic=False,
            description="Detect content_kind; supports path / JSON/YAML string / bundle {parsed,file_path}. Outputs origin, graph, error, context.",
        )
    )


__all__ = [
    "RAG_DETECT_ORIGIN_INPUT_PORTS",
    "RAG_DETECT_ORIGIN_OUTPUT_PORTS",
    "classify_content",
    "register_rag_detect_origin",
    "yaml",
]
