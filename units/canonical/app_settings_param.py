"""
Resolve unit param refs from config and assistant metadata (no GUI import).

Supported string forms (only when the whole param value is that string):

- ``settings.<key>`` — top-level key in ``config/app_settings.json``, merged with
  ``rag/ragconf.yaml`` keys ``rag_index_data_dir``, ``rag_embedding_model``, ``rag_offline``,
  ``rag_update_workflow_path``, ``doc_to_text_workflow_path``.
  Path-like keys are resolved to absolute paths under the repository root when the stored value
  is a relative path string.
- ``tool.<tool_id>.<dotted.path>`` — nested value in ``assistants/tools/<tool_id>/tool.yaml``.
- ``role.<role_id>.<dotted.path>`` — nested value in ``assistants/roles/<role_id>/role.yaml``.
  For ``role.<id>.report.output_dir``, string values are resolved as repo-relative paths when relative.

Examples: ``tool.rag_search.rag.min_score``, ``role.workflow_designer.rag.top_k``,
``settings.rag_index_data_dir``, ``role.workflow_designer.llm.ollama_model``.

Workflow / executor: ``resolve_process_graph_param_refs`` expands refs in every unit's ``params``
(recursively through dict/list) when a graph is executed.

Values are cached per file mtime. The GUI should keep the same numbers in role/tool YAML as the
single source of truth; ``settings.py`` getters delegate here for RAG knobs that moved out of
``app_settings.json``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

SETTINGS_REF_PREFIX = "settings."
TOOL_REF_PREFIX = "tool."
ROLE_REF_PREFIX = "role."

_SETTINGS_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_TOOL_ROLE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_SETTINGS_PATH = _REPO_ROOT / "config" / "app_settings.json"
_TOOLS_ROOT = _REPO_ROOT / "assistants" / "tools"
_ROLES_ROOT = _REPO_ROOT / "assistants" / "roles"

_settings_cache: dict[str, Any] | None = None
_settings_cache_mtime: float | None = None
_tool_cache: dict[str, tuple[float | None, dict[str, Any]]] = {}
_role_cache: dict[str, tuple[float | None, dict[str, Any]]] = {}

# Keys merged from ``rag/ragconf.yaml`` over JSON (RAG + workflow paths formerly in app_settings).
_RAGCONF_SETTING_KEYS = (
    "rag_index_data_dir",
    "rag_embedding_model",
    "rag_offline",
    "rag_update_workflow_path",
    "doc_to_text_workflow_path",
)

# ``settings.<key>`` values that are filesystem paths relative to the repo when not absolute.
_PATH_LIKE_SETTING_KEYS = frozenset(
    {
        "rag_index_data_dir",
        "mydata_dir",
        "chat_history_dir",
        "training_config_path",
        "best_model_path",
        "workflow_designer_prompt_path",
        "rl_coach_prompt_path",
        "create_filename_prompt_path",
        "rag_update_workflow_path",
        "doc_to_text_workflow_path",
        "debug_log_path",
        "workflow_save_path",
        "workflow_save_path_template",
        "ollama_executable_path",
    }
)


def app_settings_json_path() -> Path:
    """Path to ``config/app_settings.json`` (resolved from repo root)."""
    return _APP_SETTINGS_PATH


def read_app_settings_flat() -> dict[str, Any]:
    """Load top-level keys from ``config/app_settings.json``; empty dict if missing or invalid."""
    global _settings_cache, _settings_cache_mtime
    p = _APP_SETTINGS_PATH
    try:
        mtime = p.stat().st_mtime if p.is_file() else None
    except OSError:
        mtime = None
    if mtime is not None and _settings_cache is not None and _settings_cache_mtime == mtime:
        return _settings_cache
    if not p.is_file():
        _settings_cache = {}
        _settings_cache_mtime = mtime
        return _settings_cache
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        data = raw if isinstance(raw, dict) else {}
    except Exception:
        data = {}
    _settings_cache = data
    _settings_cache_mtime = mtime
    return data


def merged_settings_flat() -> dict[str, Any]:
    """``app_settings.json`` top-level dict overlaid with ``rag/ragconf.yaml`` RAG and workflow keys."""
    d = dict(read_app_settings_flat())
    try:
        from rag.ragconf_loader import read_ragconf

        r = read_ragconf()
        if isinstance(r, dict):
            for k in _RAGCONF_SETTING_KEYS:
                if k in r and r[k] is not None:
                    d[k] = r[k]
    except Exception:
        pass
    return d


def _repo_resolve_path_str(raw: str) -> str:
    """Turn a relative repo path into an absolute path string; leave http(s) and absolute paths."""
    s = (raw or "").strip()
    if not s or s.startswith(("http://", "https://")):
        return s
    p = Path(s).expanduser()
    if p.is_absolute():
        return str(p.resolve())
    return str((_REPO_ROOT / s).resolve())


def _maybe_resolve_settings_path(key: str, value: Any) -> Any:
    if key not in _PATH_LIKE_SETTING_KEYS or not isinstance(value, str):
        return value
    return _repo_resolve_path_str(value)


def _nested_get(root: Any, dotted: str) -> Any:
    cur: Any = root
    for part in dotted.split("."):
        if part == "":
            return None
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _cached_tool_doc(tool_id: str) -> dict[str, Any]:
    tid = (tool_id or "").strip()
    if not tid or not _TOOL_ROLE_ID_RE.match(tid):
        return {}
    p = _TOOLS_ROOT / tid / "tool.yaml"
    try:
        mtime = p.stat().st_mtime if p.is_file() else None
    except OSError:
        mtime = None
    hit = _tool_cache.get(tid)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    doc = _read_yaml_mapping(p)
    _tool_cache[tid] = (mtime, doc)
    return doc


def _cached_role_doc(role_id: str) -> dict[str, Any]:
    rid = (role_id or "").strip()
    if not rid or not _TOOL_ROLE_ID_RE.match(rid):
        return {}
    p = _ROLES_ROOT / rid / "role.yaml"
    try:
        mtime = p.stat().st_mtime if p.is_file() else None
    except OSError:
        mtime = None
    hit = _role_cache.get(rid)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    doc = _read_yaml_mapping(p)
    _role_cache[rid] = (mtime, doc)
    return doc


def is_param_ref(value: Any) -> bool:
    """True if ``value`` is a non-empty string starting with ``settings.``, ``tool.``, or ``role.``."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    return (
        s.startswith(SETTINGS_REF_PREFIX)
        or s.startswith(TOOL_REF_PREFIX)
        or s.startswith(ROLE_REF_PREFIX)
    )


def is_settings_ref(value: Any) -> bool:
    return isinstance(value, str) and value.strip().startswith(SETTINGS_REF_PREFIX)


def resolve_param_ref(value: str) -> Any:
    """
    Resolve a ref string. Returns ``None`` if the ref is malformed or the path is missing.
    For ``settings.<key>``, missing key returns ``None``.
    """
    s = (value or "").strip()
    if not s:
        return None
    if s.startswith(SETTINGS_REF_PREFIX):
        key = s[len(SETTINGS_REF_PREFIX) :].strip()
        if not key or not _SETTINGS_KEY_RE.match(key):
            return None
        v = merged_settings_flat().get(key)
        return _maybe_resolve_settings_path(key, v)

    if s.startswith(TOOL_REF_PREFIX):
        rest = s[len(TOOL_REF_PREFIX) :]
        m = re.match(r"^([a-z][a-z0-9_]*)\.(.+)$", rest)
        if not m:
            return None
        tid, path = m.group(1), m.group(2)
        if not path:
            return None
        return _nested_get(_cached_tool_doc(tid), path)

    if s.startswith(ROLE_REF_PREFIX):
        rest = s[len(ROLE_REF_PREFIX) :]
        m = re.match(r"^([a-z][a-z0-9_]*)\.(.+)$", rest)
        if not m:
            return None
        rid, path = m.group(1), m.group(2)
        if not path:
            return None
        v = _nested_get(_cached_role_doc(rid), path)
        if path == "report.output_dir" and isinstance(v, str):
            return _repo_resolve_path_str(v)
        return v

    return None


def resolve_settings_ref(value: Any) -> Any:
    """
    Back-compat: if ``value`` is a ``settings.<key>`` string, resolve it (merged JSON + ragconf for RAG keys);
    otherwise return ``value`` unchanged.
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s.startswith(SETTINGS_REF_PREFIX):
        return value
    return resolve_param_ref(s)


def coerce_int_param(value: Any) -> int | None:
    """Int for unit params: literals, numeric strings, or ``settings.*`` / ``tool.*`` / ``role.*`` refs."""
    if value is None:
        return None
    if type(value) is bool:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if is_param_ref(s):
            r = resolve_param_ref(s)
            if r is None:
                return None
            value = r
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def coerce_float_param(value: Any) -> float | None:
    """Float for unit params: literals, numeric strings, or param refs."""
    if value is None:
        return None
    if type(value) is bool:
        return None
    if isinstance(value, float):
        return float(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if is_param_ref(s):
            r = resolve_param_ref(s)
            if r is None:
                return None
            value = r
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def deep_resolve_param_refs(obj: Any) -> Any:
    """Recursively resolve ``settings.*``, ``tool.*``, and ``role.*`` string leaves in dict/list structures."""
    if isinstance(obj, dict):
        return {k: deep_resolve_param_refs(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_resolve_param_refs(x) for x in obj]
    if isinstance(obj, str):
        s = obj.strip()
        if is_param_ref(s):
            resolved = resolve_param_ref(s)
            return deep_resolve_param_refs(resolved)
        return obj
    return obj


def resolve_process_graph_param_refs(graph: Any) -> Any:
    """
    Return a copy of ``graph`` with each unit's ``params`` deep-resolved via ``deep_resolve_param_refs``.
    Accepts a ``ProcessGraph`` pydantic model.
    """
    units = getattr(graph, "units", None)
    if not isinstance(units, list):
        return graph
    new_units = []
    for u in units:
        params = getattr(u, "params", None) or {}
        resolved = deep_resolve_param_refs(dict(params))
        if hasattr(u, "model_copy"):
            new_units.append(u.model_copy(update={"params": resolved}))
        else:
            new_units.append(u)
    if hasattr(graph, "model_copy"):
        return graph.model_copy(update={"units": new_units})
    return graph
