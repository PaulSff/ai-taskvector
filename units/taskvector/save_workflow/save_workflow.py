from __future__ import annotations

import datetime
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from config.settings import (
    REPO_ROOT,
    get_workflow_project_name,
    get_workflow_save_path_template,
)

# Application types/settings — required. Do not hardcode defaults here.
from core.schemas.primitives import Data
from core.schemas.process_graph import ProcessGraph
from services.logging import setup_colored_logging
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

logger = setup_colored_logging(logging.DEBUG)

type GraphInput = ProcessGraph | Data

@dataclass(frozen=True)
class _SaveResult:
    saved: bool
    path: Path | None
    reason: str  # "saved" | "no_changes" | "no_graph" | "error" | "validation:..."


def _now_timestamp() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")


def resolve_workflow_save_path(
    template: str, *, project_name: str, timestamp: str
) -> str:
    return (
        (template or "")
        .replace(PLACEHOLDER_PROJECT_NAME, project_name)
        .replace(PLACEHOLDER_TIMESTAMP, timestamp)
    )


def _graph_to_payload(graph: GraphInput | None) -> Data:
    """
    Normalize graph into a dictionary suitable for saving.

    - If graph is a dict, attempt ProcessGraph.model_validate(graph) and
      return model_dump(by_alias=True) on success; otherwise return dict(graph).
    - If graph is a model-like object with .model_dump, call it and require
      a dict result.
    - If graph has a __dict__ mapping, return a dict copy.
    - If graph is None or none of the above yield a dict, raise ValueError.
    """
    if graph is None:
        raise ValueError("no_graph")

    if isinstance(graph, dict):
        if hasattr(ProcessGraph, "model_validate"):
            try:
                validated = ProcessGraph.model_validate(graph)
                result = validated.model_dump(
                    by_alias=True,
                    mode="json",
                )
                if isinstance(result, dict):
                    return result
            except ValidationError:
                pass

        return dict(graph)

    model_dump = getattr(graph, "model_dump", None)
    if callable(model_dump):
        try:
            result = model_dump(by_alias=True)
        except TypeError:
            result = model_dump()

        if isinstance(result, dict):
            return result

        fallback_dump = getattr(result, "model_dump", None)
        if callable(fallback_dump):
            try:
                res2 = fallback_dump(by_alias=True)
            except TypeError:
                res2 = fallback_dump()
            except ValidationError:
                pass
            else:
                if isinstance(res2, dict):
                    return res2

    obj_dict = getattr(graph, "__dict__", None)
    if isinstance(obj_dict, dict):
        return dict(obj_dict)

    try:
        s = json.dumps(graph, default=lambda o: getattr(o, "__dict__", None))
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    raise ValueError("invalid_graph")


def _graph_json_bytes(graph: GraphInput | None) -> bytes:
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
        "todo_lists",
    )
    ordered = {k: payload[k] for k in order if k in payload}
    for k, v in payload.items():
        if k not in ordered:
            ordered[k] = v
    s = json.dumps(ordered, indent=2, sort_keys=False, ensure_ascii=False)
    return s.encode("utf-8")


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _latest_saved_file(project_dir: Path, ext: str = ".json") -> Path | None:
    if not project_dir.exists() or not project_dir.is_dir():
        return None
    files = sorted([p for p in project_dir.glob(f"*{ext}") if p.is_file()])
    return files[-1] if files else None


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _dump_yaml_bytes(obj: Data) -> bytes:
    try:
        import yaml  # PyYAML
    except Exception as exc:
        raise RuntimeError("yaml not available") from exc

    s = yaml.safe_dump(obj, sort_keys=False)
    return s.encode("utf-8")


def _save_workflow_version(
    graph: GraphInput | None,
    *,
    project_name: str | None = None,
    template: str | None = None,
    repo_root: str | Path | None = None,
    fmt: str = "json",
) -> _SaveResult:
    if graph is None:
        return _SaveResult(saved=False, path=None, reason="no_graph")

    project_name = (project_name or get_workflow_project_name()).strip() or "my_project"

    # Prefer the explicit template; otherwise use the settings function.
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
        if not path.suffix or path.suffix.lower() != ext:
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
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
):
    raw_graph = inputs.get("graph")

    if raw_graph is None:
        graph: GraphInput | None = None
        logger.warning("SaveWorkflow received no graph")
    elif isinstance(raw_graph, (ProcessGraph, dict)):
        graph = raw_graph
    else:
        graph = None
        logger.warning(
            "SaveWorkflow received unsupported graph type: %s",
            type(raw_graph).__name__,
        )

    raw_format = params.get("format")
    fmt = raw_format.lower() if isinstance(raw_format, str) else "json"

    # Template override parameter takes precedence.
    raw_template = params.get("workflow_save_path")
    if not isinstance(raw_template, str):
        raw_template = params.get("workflow_save_path_template")

    template_override = (
        raw_template if isinstance(raw_template, str) else None
    )

    raw_project_name = params.get("project_name")
    project_name_override = (
        raw_project_name if isinstance(raw_project_name, str) else None
    )

    raw_repo_root = params.get("repo_root")
    repo_root_override = (
        raw_repo_root
        if isinstance(raw_repo_root, (str, Path))
        else None
    )

    try:
        result = _save_workflow_version(
            graph,
            project_name=project_name_override,
            template=template_override,
            repo_root=repo_root_override,
            fmt=fmt,
        )
    except Exception:
        logger.exception("SaveWorkflow crashed while saving")
        return {
            "saved_at": None,
            "error": "save failed",
        }, state

    logger.info(
        "SaveWorkflow completed: saved=%s, path=%s, reason=%s",
        result.saved,
        result.path,
        result.reason,
    )

    if result.saved and result.path is not None:
        outputs = {
            "saved_at": str(result.path),
            "error": None,
        }
    else:
        if result.reason == "no_changes":
            error = "no changes to save"
        elif result.reason == "no_graph":
            error = "no workflow loaded"
        elif result.reason.startswith("validation:"):
            message = result.reason.split(":", 1)[1]
            error = f"validation failed: {message}"
        else:
            error = "save failed"

        outputs = {
            "saved_at": None,
            "error": error,
        }

    return outputs, state


def register_save_workflow() -> None:
    register_unit(
        UnitSpec(
            type_name="SaveWorkflow",
            input_ports=SAVE_WORKFLOW_INPUT_PORTS,
            output_ports=SAVE_WORKFLOW_OUTPUT_PORTS,
            step_fn=_save_workflow_step,
            environment_tags=["taskvector"],
            environment_tags_are_agnostic=False,
            description=(
                "Save workflow graph to versioned JSON/YAML file. Uses MD5 canonical JSON for change detection. "
                "Params: format (json|yaml), workflow_save_path (template override), project_name, repo_root."
            ),
        )
    )


__all__ = ["register_save_workflow"]
