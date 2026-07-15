"""
Load and optionally update ``rag/ragconf.yaml`` (index dir, embedding model, offline flag,
``rag_update_workflow_path``, ``doc_to_text_workflow_path``, mydata refresh workflow paths).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from gui.components.settings import get_rag_config_path

import yaml

def ensure_ragconf_exists() -> Path:
    """Return rag config path and create ragconf.yaml if missing."""
    p = get_rag_config_path()  # returns the full path

    # ensure parent dir exists
    p.parent.mkdir(parents=True, exist_ok=True)

    # create empty config if file is missing
    if not p.is_file():
        p.write_text(yaml.safe_dump({}, sort_keys=False), encoding="utf-8")

    return p

# Rag config file is set in the main app.settings.json
RAGCONF_PATH = ensure_ragconf_exists()

DEFAULT_RAG_INDEX_DATA_DIR = "rag/.rag_index_data"
DEFAULT_RAG_INDEX_WORKFLOW_SERVER_ENDPOINT = "tcp://127.0.0.1:6669"
DEFAULT_RAG_INDEX_RESPONSE_ENDPOINT = "tcp://127.0.0.1:6679"
DEFAULT_RAG_INDEX_RESPONSE_TIMEOUT_S = 6000.0
DEFAULT_RAG_UPDATE_WORKFLOW_SERVER_ENDPOINT = "tcp://127.0.0.1:6666"
DEFAULT_RAG_UPDATE_RESPONSE_ENDPOINT = "tcp://127.0.0.1:6676"
DEFAULT_RAG_UPDATE_RESPONSE_TIMEOUT_S = 6000.0
DEFAULT_RAG_DOWNLOADS_DIR = "mydata/rag/downloads"
DEFAULT_RAG_EMBEDDING_MODEL = (
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
)
DEFAULT_RAG_OFFLINE = False
DEFAULT_RAG_INCLUDE_PICTURES = False
DEFAULT_RAG_IMAGES_SCALE = 2.0
DEFAULT_RAG_PICTURE_CLASSIFICATION = False
DEFAULT_RAG_PICTURE_DESCRIPTION = False
DEFAULT_RAG_PICTURE_DESCRIPTION_MODEL = "smolvlm"
DEFAULT_RAG_PICTURE_DESCRIPTION_API_URL = ""
DEFAULT_RAG_CODE_ENRICHMENT = False
DEFAULT_RAG_FORMULA_ENRICHMENT = False
DEFAULT_RAG_UPDATE_WORKFLOW_PATH = "rag/workflows/rag_update.json"
DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH = "rag/workflows/doc_to_text.json"
DEFAULT_MYDATA_FILE_MANAGER_REFRESH_WORKFLOW_PATH = (
    "rag/workflows/mydata_file_manager_refresh.json"
)
DEFAULT_MYDATA_STORAGE_REPORT_ONLY_WORKFLOW_PATH = (
    "rag/workflows/mydata_storage_report_only.json"
)
DEFAULT_RAG_UPLOAD_PIPELINE_WORKFLOW_PATH = "rag/workflows/rag_upload_pipeline.json"
DEFAULT_RAG_RAW_SEARCH_WORKFLOW_PATH = "rag/workflows/rag_raw_search.json"
DEFAULT_RAG_DELETE_FROM_INDEX_WORKFLOW_PATH = "rag/workflows/rag_delete_from_index.json"
DEFAULT_RAG_WORKFLOW_SUFFIX = ".json"
DEFAULT_RAG_INDEX_STATE_FILENAME = ".rag_index_state.json"
DEFAULT_NOINDEX_FILENAME = ".noindex.txt"
DEFAULT_RAG_SKIP_TRACK_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
    }
)

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

def rag_index_workflow_server_endpoint_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_index_workflow_server_endpoint")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_INDEX_WORKFLOW_SERVER_ENDPOINT
    return str(v).strip()


def rag_index_response_endpoint_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_index_response_endpoint")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_INDEX_RESPONSE_ENDPOINT
    return str(v).strip()


def rag_index_response_timeout_s_raw() -> float:
    d = read_ragconf()
    v = d.get("rag_index_response_timeout_s")
    if v is None:
        return DEFAULT_RAG_INDEX_RESPONSE_TIMEOUT_S
    try:
        return float(v)
    except (TypeError, ValueError):
        return DEFAULT_RAG_INDEX_RESPONSE_TIMEOUT_S


def rag_update_workflow_server_endpoint_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_update_workflow_server_endpoint")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_UPDATE_WORKFLOW_SERVER_ENDPOINT
    return str(v).strip()


def rag_update_response_endpoint_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_update_response_endpoint")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_UPDATE_RESPONSE_ENDPOINT
    return str(v).strip()


def rag_update_response_timeout_s_raw() -> float:
    d = read_ragconf()
    v = d.get("rag_update_response_timeout_s")
    if v is None:
        return DEFAULT_RAG_UPDATE_RESPONSE_TIMEOUT_S
    try:
        return float(v)
    except (TypeError, ValueError):
        return DEFAULT_RAG_UPDATE_RESPONSE_TIMEOUT_S

def rag_downloads_dir_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_downloads_dir")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_DOWNLOADS_DIR
    return str(v).strip()


def rag_embedding_model_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_embedding_model")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_EMBEDDING_MODEL
    return str(v).strip()


def rag_picture_description_model_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_picture_description_model")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_PICTURE_DESCRIPTION_MODEL
    return str(v).strip()


def rag_picture_description_api_url_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_picture_description_api_url")
    if v is None:
        return DEFAULT_RAG_PICTURE_DESCRIPTION_API_URL
    return str(v).strip()


def rag_include_pictures_raw() -> bool:
    d = read_ragconf()
    if "rag_include_pictures" not in d:
        return DEFAULT_RAG_INCLUDE_PICTURES
    return bool(d.get("rag_include_pictures"))


def rag_images_scale_raw() -> float:
    d = read_ragconf()
    v = d.get("rag_images_scale")
    if v is None:
        return DEFAULT_RAG_IMAGES_SCALE
    try:
        return float(v)
    except (TypeError, ValueError):
        return DEFAULT_RAG_IMAGES_SCALE


def rag_picture_classification_raw() -> bool:
    d = read_ragconf()
    if "rag_picture_classification" not in d:
        return DEFAULT_RAG_PICTURE_CLASSIFICATION
    return bool(d.get("rag_picture_classification"))


def rag_picture_description_raw() -> bool:
    d = read_ragconf()
    if "rag_picture_description" not in d:
        return DEFAULT_RAG_PICTURE_DESCRIPTION
    return bool(d.get("rag_picture_description"))


def rag_code_enrichment_raw() -> bool:
    d = read_ragconf()
    if "rag_code_enrichment" not in d:
        return DEFAULT_RAG_CODE_ENRICHMENT
    return bool(d.get("rag_code_enrichment"))


def rag_formula_enrichment_raw() -> bool:
    d = read_ragconf()
    if "rag_formula_enrichment" not in d:
        return DEFAULT_RAG_FORMULA_ENRICHMENT
    return bool(d.get("rag_formula_enrichment"))


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


def mydata_file_manager_refresh_workflow_path_raw() -> str:
    d = read_ragconf()
    v = d.get("mydata_file_manager_refresh_workflow_path")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_MYDATA_FILE_MANAGER_REFRESH_WORKFLOW_PATH
    return str(v).strip()


def mydata_storage_report_only_workflow_path_raw() -> str:
    d = read_ragconf()
    v = d.get("mydata_storage_report_only_workflow_path")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_MYDATA_STORAGE_REPORT_ONLY_WORKFLOW_PATH
    return str(v).strip()


def rag_upload_pipeline_workflow_path_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_upload_pipeline_workflow_path")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_UPLOAD_PIPELINE_WORKFLOW_PATH
    return str(v).strip()


def rag_raw_search_workflow_path_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_raw_search_workflow_path")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_RAW_SEARCH_WORKFLOW_PATH
    return str(v).strip()


def rag_delete_from_index_workflow_path_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_delete_from_index_workflow_path")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_DELETE_FROM_INDEX_WORKFLOW_PATH
    return str(v).strip()


def rag_workflow_suffix_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_workflow_suffix")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_WORKFLOW_SUFFIX
    return str(v).strip()


def rag_index_state_filename_raw() -> str:
    d = read_ragconf()
    v = d.get("rag_index_state_filename")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_RAG_INDEX_STATE_FILENAME
    return str(v).strip()


def noindex_filename_raw() -> str:
    d = read_ragconf()
    v = d.get("noindex_filename")
    if v is None or (isinstance(v, str) and not v.strip()):
        return DEFAULT_NOINDEX_FILENAME
    return str(v).strip()


def _as_frozenset_of_str(items: Iterable) -> frozenset:
    return frozenset(str(i).strip() for i in items if i is not None and str(i).strip())


def get_rag_skip_track_dir_names() -> frozenset:
    """
    Read rag_skip_track_dir_names from ragconf (list of names) and return a frozenset
    matching the format of DEFAULT_RAG_SKIP_TRACK_DIR_NAMES. If the config key is
    missing or invalid, return the DEFAULT_RAG_SKIP_TRACK_DIR_NAMES.
    """
    d = read_ragconf()
    v = d.get("rag_skip_track_dir_names")
    # Accept list/tuple/iterable of strings; if it's a single string, treat as newline/comma separated
    if v is None:
        return DEFAULT_RAG_SKIP_TRACK_DIR_NAMES

    # If someone put a string, split by newlines/commas
    if isinstance(v, str):
        # allow both comma and newline separated values
        parts = [p for line in v.splitlines() for p in line.split(",")]
        items = [p.strip() for p in parts if p.strip()]
        return _as_frozenset_of_str(items) or DEFAULT_RAG_SKIP_TRACK_DIR_NAMES

    # If it's an iterable (list/tuple), coerce entries to strings
    try:
        return _as_frozenset_of_str(v) or DEFAULT_RAG_SKIP_TRACK_DIR_NAMES
    except TypeError:
        return DEFAULT_RAG_SKIP_TRACK_DIR_NAMES


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
        yaml.safe_dump(
            doc, sort_keys=False, allow_unicode=True, default_flow_style=False
        ),
        encoding="utf-8",
    )
    clear_ragconf_cache()
