from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

# Application types/settings — required. Do not hardcode defaults here.
from core.schemas.process_graph import ProcessGraph
from gui.components.settings import (
    REPO_ROOT,
    get_workflow_project_name,
    get_workflow_save_path_template,
)
from units.registry import UnitSpec, register_unit

PLACEHOLDER_PROJECT_NAME = "$PROJECT_NAME$"
PLACEHOLDER_TIMESTAMP = "$YY-MM-DD-HHMMSS$"

SAVE_WORKFLOW_INPUT_PORTS = [
    ("graph", "Any"),
]
SAVE_WORKFLOW_OUTPUT_PORTS = [
    ("saved_at", "Any"),
    ("error", "Any"),
]


def _now_timestamp() -> str:
    return datetime.now().strftime("%y-%m-%d-%H%M%S")


def resolve_workflow_save_path(
    template: str, *, project_name: str, timestamp: str
) -> str:
    return (
        (template or "")
        .replace(PLACEHOLDER_PROJECT_NAME, project_name)
        .replace(PLACEHOLDER_TIMESTAMP, timestamp)
    )


def _graph_to_payload(graph: Optional[Union[dict, Any]]) -> dict:
    """
    Normalize graph into a dict suitable for saving.

    - If graph is a dict, attempt ProcessGraph.model_validate(graph) and return model_dump(by_alias=True) on success,
      otherwise return dict(graph).
    - If graph is a model-like object with .model_dump, call that and require a dict result.
    - If graph has a __dict__ mapping, return a dict copy.
    - If graph is None or none of the above yield a dict, raise ValueError.
    """
    if graph is None:
        raise ValueError("no_graph")

    # If it's a dict, try to validate/normalize via ProcessGraph, but fall back to a plain dict.
    if isinstance(graph, dict):
        if hasattr(ProcessGraph, "model_validate"):
            try:
                validated = ProcessGraph.model_validate(graph)
                result = validated.model_dump(by_alias=True)
                if isinstance(result, dict):
                    return result
            except Exception:
                # fall through to returning plain dict
                pass
        return dict(graph)

    # If it has model_dump, call it safely and ensure a dict is returned.
    model_dump = getattr(graph, "model_dump", None)
    if callable(model_dump):
        try:
            result = model_dump(by_alias=True)
        except TypeError:
            result = model_dump()
        if isinstance(result, dict):
            return result
        # If result is a model instance, try to call model_dump on it as a defensive step
        fallback_dump = getattr(result, "model_dump", None)
        if callable(fallback_dump):
            try:
                res2 = fallback_dump(by_alias=True)
                if isinstance(res2, dict):
                    return res2
            except Exception:
                pass

    # Try __dict__ if it's a mapping
    obj_dict = getattr(graph, "__dict__", None)
    if isinstance(obj_dict, dict):
        return dict(obj_dict)

    # Last resort: try JSON round-trip to obtain a dict
    try:
        s = json.dumps(graph, default=lambda o: getattr(o, "__dict__", None))
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Can't produce a valid dict payload — caller should handle this as an error.
    raise ValueError("invalid_graph")


def _graph_json_bytes(graph: Optional[Union[dict, Any]]) -> bytes:
    payload = _graph_to_payload(graph)
    order = (
        "environment_type",
        "environments",
        "units",
        "connections",
        "code_blocks",
        "layout",
        "origin",
        "origin_format",
        "runtime",
        "tabs",
        "metadata",
        "comments",
        "todo_list",
    )
    ordered = {k: payload[k] for k in order if k in payload}
    for k, v in payload.items():
        if k not in ordered:
            ordered[k] = v
    s = json.dumps(ordered, indent=2, sort_keys=False, ensure_ascii=False)
    return s.encode("utf-8")


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _latest_saved_file(project_dir: Path, ext: str = ".json") -> Optional[Path]:
    if not project_dir.exists() or not project_dir.is_dir():
        return None
    files = sorted([p for p in project_dir.glob(f"*{ext}") if p.is_file()])
    return files[-1] if files else None


@dataclass(frozen=True)
class _SaveResult:
    saved: bool
    path: Optional[Path]
    reason: str  # "saved" | "no_changes" | "no_graph" | "error" | "validation:..."


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _dump_yaml_bytes(obj: dict) -> bytes:
    try:
        import yaml  # PyYAML
    except Exception as exc:
        raise RuntimeError("yaml not available") from exc
    s = yaml.safe_dump(obj, sort_keys=False)
    return s.encode("utf-8")


def _save_workflow_version(
    graph: Optional[Union[dict, Any]],
    *,
    project_name: Optional[str] = None,
    template: Optional[str] = None,
    repo_root: Optional[Union[str, Path]] = None,
    fmt: str = "json",
) -> _SaveResult:
    if graph is None:
        return _SaveResult(saved=False, path=None, reason="no_graph")

    project_name = (project_name or get_workflow_project_name()).strip() or "my_project"
    # Template: prefer explicit template param; otherwise use settings function (no hardcoded string).
    template = (template or get_workflow_save_path_template()).strip()
    if not template:
        return _SaveResult(saved=False, path=None, reason="error")

    ts = _now_timestamp()
    rel = resolve_workflow_save_path(
        template, project_name=project_name, timestamp=ts
    ).strip()

    if repo_root and not Path(rel).is_absolute():
        path = Path(repo_root) / rel
    else:
        path = Path(rel) if Path(rel).is_absolute() else (REPO_ROOT / rel)
    project_dir = path.parent

    try:
        if fmt.lower() == "json":
            # _graph_json_bytes may raise ValueError from validation -> catch below
            data = _graph_json_bytes(graph)
            ext = ".json"
        elif fmt.lower() == "yaml":
            # _graph_to_payload may raise ValueError from validation -> catch below
            payload = _graph_to_payload(graph)
            data = _dump_yaml_bytes(payload)
            ext = ".yaml"
        else:
            return _SaveResult(saved=False, path=None, reason="error")

        cur_hash = _md5_hex(data)

        latest = _latest_saved_file(project_dir, ext=ext)
        if latest is not None:
            latest_bytes = latest.read_bytes()
            if _md5_hex(latest_bytes) == cur_hash:
                return _SaveResult(saved=False, path=latest, reason="no_changes")

        project_dir.mkdir(parents=True, exist_ok=True)
        if not path.suffix:
            path = path.with_suffix(ext)
        elif path.suffix.lower() != ext:
            path = path.with_suffix(ext)
        _write_bytes(path, data)
        return _SaveResult(saved=True, path=path, reason="saved")
    except ValueError as e:
        # Map validation/graph conversion issues to a validation reason (preserves message)
        return _SaveResult(saved=False, path=None, reason=f"validation:{e}")
    except RuntimeError:
        return _SaveResult(saved=False, path=path, reason="error")
    except OSError:
        return _SaveResult(saved=False, path=path, reason="error")


def _save_workflow_step(
    params: dict[str, Any], inputs: dict[str, Any], state: dict[str, Any], dt: float
):
    graph = inputs.get("graph")
    fmt = (params.get("format") or "json").lower()
    # Template override param takes precedence. If not provided, use settings function.
    template_override = params.get("workflow_save_path") or params.get(
        "workflow_save_path_template"
    )
    project_name_override = params.get("project_name")
    repo_root_override = params.get("repo_root")

    result = _save_workflow_version(
        graph,
        project_name=project_name_override,
        template=template_override,
        repo_root=repo_root_override,
        fmt=fmt,
    )

    if result.saved and result.path is not None:
        outputs = {"saved_at": str(result.path), "error": None}
    else:
        if result.reason == "no_changes":
            err = {"error": "no changes to save"}
        elif result.reason == "no_graph":
            err = {"error": "no workflow loaded"}
        elif result.reason.startswith("validation:"):
            msg = result.reason.split(":", 1)[1]
            err = {"error": f"validation failed: {msg}"}
        else:
            err = {"error": "save failed"}
        outputs = {"saved_at": None, "error": err}
    return outputs, state


def register_save_workflow() -> None:
    register_unit(
        UnitSpec(
            type_name="SaveWorkflow",
            input_ports=SAVE_WORKFLOW_INPUT_PORTS,
            output_ports=SAVE_WORKFLOW_OUTPUT_PORTS,
            step_fn=_save_workflow_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Save workflow graph to versioned JSON/YAML file. Uses MD5 canonical JSON for change detection. "
                "Params: format (json|yaml), workflow_save_path (template override), project_name, repo_root."
            ),
        )
    )


__all__ = ["register_save_workflow"]
