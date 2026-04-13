"""
Load and optionally update ``rag/ragconf.yaml`` (index dir, embedding model, offline flag,
``rag_update_workflow_path``, ``doc_to_text_workflow_path``).

Used by ``gui.components.settings`` and by ``python -m rag update`` so RAG does not depend on
``config/app_settings.json`` for these keys.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_RAG_DIR = Path(__file__).resolve().parent
RAGCONF_PATH = _RAG_DIR / "ragconf.yaml"

DEFAULT_RAG_INDEX_DATA_DIR = "rag/.rag_index_data"
DEFAULT_RAG_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RAG_OFFLINE = False
DEFAULT_RAG_UPDATE_WORKFLOW_PATH = "rag/workflows/rag_update.json"
DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH = "rag/workflows/doc_to_text.json"

_cache: dict[str, Any] | None = None
_cache_mtime: float | None = None


def ragconf_path() -> Path:
    return RAGCONF_PATH


def clear_ragconf_cache() -> None:
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = None


def read_ragconf() -> dict[str, Any]:
    """Return merged mapping from ``ragconf.yaml``; empty dict if missing or invalid."""
    global _cache, _cache_mtime
    p = RAGCONF_PATH
    try:
        mtime = p.stat().st_mtime if p.is_file() else None
    except OSError:
        mtime = None
    if _cache is not None and _cache_mtime == mtime:
        return _cache
    if not p.is_file():
        _cache = {}
        _cache_mtime = mtime
        return _cache
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        data = raw if isinstance(raw, dict) else {}
    except Exception:
        data = {}
    _cache = data
    _cache_mtime = mtime
    return data


def rag_index_data_dir_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_index_data_dir")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_INDEX_DATA_DIR
    return str(v).strip()


def rag_embedding_model_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_embedding_model")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_EMBEDDING_MODEL
    return str(v).strip()


def rag_offline_raw() -> bool:
    d = read_ragconf()
    if "rag_offline" not in d:
        return bool(DEFAULT_RAG_OFFLINE)
    return bool(d.get("rag_offline"))


def rag_update_workflow_path_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_update_workflow_path")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_UPDATE_WORKFLOW_PATH
    return str(v).strip()


def doc_to_text_workflow_path_raw() -> str:
    d = read_ragconf()
    v = d.get("doc_to_text_workflow_path")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH
    return str(v).strip()


def update_ragconf(patch: dict[str, Any]) -> None:
    """Merge ``patch`` into ``ragconf.yaml`` (RAG keys including workflow paths)."""
    if not patch:
        return
    p = RAGCONF_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = read_ragconf()
    if not isinstance(doc, dict):
        doc = {}
    doc = dict(doc)
    for k, v in patch.items():
        if v is not None:
            doc[k] = v
    p.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    clear_ragconf_cache()
