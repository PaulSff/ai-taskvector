"""
RAG index version control: manifests, MD5 hashes, incremental update of units/ and mydata/.
Used by the Flet app at startup and by `python -m rag update`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

Manifest = dict[str, str]

RAG_DOC_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
RAG_WORKFLOW_SUFFIX = ".json"
RAG_INDEX_STATE_FILENAME = ".rag_index_state.json"


def _folder_hash(
    root: Path,
    *,
    suffixes: set[str],
    exclude_path: Callable[[Path], bool] | None = None,
) -> str | None:
    """MD5 of (sorted relative path + content) for all files under root with given suffixes."""
    if not root.is_dir():
        return None
    paths = [
        p for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in suffixes
        and (exclude_path is None or not exclude_path(p))
    ]
    if not paths:
        return None
    paths.sort(key=lambda p: str(p))
    h = hashlib.md5()
    for p in paths:
        rel = str(p.relative_to(root))
        h.update(rel.encode("utf-8"))
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def _compute_manifest(
    root: Path,
    *,
    suffixes: set[str],
    exclude_path: Callable[[Path], bool] | None = None,
) -> Manifest:
    """Per-file content hash for all files under root. Returns dict[relative_path_str, md5_hex]."""
    out: Manifest = {}
    if not root.is_dir():
        return out
    paths = [
        p for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in suffixes
        and (exclude_path is None or not exclude_path(p))
    ]
    paths.sort(key=lambda p: str(p))
    for p in paths:
        rel = str(p.relative_to(root)).replace("\\", "/")
        try:
            out[rel] = hashlib.md5(p.read_bytes()).hexdigest()
        except OSError:
            pass
    return out


def _mydata_exclude(root: Path, state_filename: str = RAG_INDEX_STATE_FILENAME) -> Callable[[Path], bool]:
    """Return exclude_path for mydata: chroma_db and state file under root."""

    def exclude(p: Path) -> bool:
        try:
            if "chroma_db" in p.relative_to(root).parts:
                return True
        except ValueError:
            pass
        if p.name == state_filename:
            return True
        return False

    return exclude


def _mydata_folder_hash(rag_index_dir: Path) -> str | None:
    """MD5 of RAG-relevant files under rag_index_dir, excluding chroma_db and state file."""
    root = rag_index_dir.resolve()
    if not root.is_dir():
        return None
    return _folder_hash(
        root,
        suffixes=RAG_DOC_SUFFIXES | {RAG_WORKFLOW_SUFFIX},
        exclude_path=_mydata_exclude(root),
    )


def load_state(rag_index_dir: Path) -> dict:
    """Return state from .rag_index_state.json. Keys: units_hash, mydata_hash, units_files, mydata_files."""
    out: dict = {
        "units_hash": None,
        "mydata_hash": None,
        "units_files": None,
        "mydata_files": None,
    }
    state_path = rag_index_dir.resolve() / RAG_INDEX_STATE_FILENAME
    if not state_path.is_file():
        return out
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return out
        for key in out:
            if data.get(key) is not None:
                out[key] = data[key]
    except (OSError, json.JSONDecodeError):
        pass
    return out


def save_state(
    rag_index_dir: Path,
    *,
    units_hash: str | None = None,
    mydata_hash: str | None = None,
    units_files: Manifest | None = None,
    mydata_files: Manifest | None = None,
) -> None:
    """Merge and write state to .rag_index_state.json."""
    state_path = (rag_index_dir / RAG_INDEX_STATE_FILENAME).resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    current = load_state(rag_index_dir)
    if units_hash is not None:
        current["units_hash"] = units_hash
    if mydata_hash is not None:
        current["mydata_hash"] = mydata_hash
    if units_files is not None:
        current["units_files"] = units_files
    if mydata_files is not None:
        current["mydata_files"] = mydata_files
    state_path.write_text(
        json.dumps(
            {
                "units_hash": current["units_hash"],
                "mydata_hash": current["mydata_hash"],
                "units_files": current.get("units_files"),
                "mydata_files": current.get("mydata_files"),
            },
            indent=0,
        ),
        encoding="utf-8",
    )


def need_indexing(rag_index_dir: Path, units_dir: Path) -> tuple[bool, bool, str]:
    """Quick check: (need_units, need_mydata, message). Does not index."""
    try:
        state = load_state(rag_index_dir)
    except Exception:
        return (True, True, "check failed, will try index")

    need_units = False
    need_mydata = False
    if units_dir.resolve().is_dir():
        paths_u = [p for p in units_dir.rglob("*") if p.is_file() and p.suffix.lower() in RAG_DOC_SUFFIXES]
        if paths_u:
            current_u = _folder_hash(units_dir, suffixes=RAG_DOC_SUFFIXES)
            if current_u is not None and current_u != state.get("units_hash"):
                need_units = True
    if rag_index_dir.resolve().is_dir():
        current_m = _mydata_folder_hash(rag_index_dir)
        if current_m is not None and current_m != state.get("mydata_hash"):
            need_mydata = True

    if not need_units and not need_mydata:
        return (False, False, "up to date")
    return (need_units, need_mydata, "units changed" if need_units else "mydata changed")


def _index_folder_incremental(
    index: Any,
    root: Path,
    suffixes: set[str],
    exclude_path: Callable[[Path], bool] | None,
    saved_manifest: Manifest | None,
    rag_index_dir: Path,
    *,
    folder_hash: str,
    save_units: bool,
) -> tuple[int, str | None]:
    """Index only changed/new files. Returns (count_added, error_message)."""
    current_manifest = _compute_manifest(root, suffixes=suffixes, exclude_path=exclude_path)
    if not current_manifest:
        return (0, None)
    saved = saved_manifest or {}
    to_remove = set(saved) - set(current_manifest)
    to_add = [rel for rel in current_manifest if current_manifest[rel] != saved.get(rel)]
    if not to_remove and not to_add:
        return (0, None)
    delete_abs = [str((root / rel).resolve()) for rel in (to_remove | set(to_add))]
    add_abs = [str((root / rel).resolve()) for rel in to_add]
    index.delete_by_file_paths(delete_abs)
    added = 0
    if add_abs:
        added = index.add_documents_and_index(add_abs)
    if save_units:
        save_state(rag_index_dir, units_hash=folder_hash, units_files=current_manifest)
    else:
        save_state(rag_index_dir, mydata_hash=folder_hash, mydata_files=current_manifest)
    return (added, None)


def run_update(
    rag_index_dir: Path,
    units_dir: Path,
    *,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    """
    Update RAG index from units_dir and rag_index_dir (mydata) when content has changed.
    Returns dict: ok, need_index, units_count, mydata_count, error, message, details.
    """
    result: dict[str, Any] = {
        "ok": False,
        "need_index": False,
        "units_count": 0,
        "mydata_count": 0,
        "error": None,
        "message": "",
        "details": "",
    }
    rag_index_dir = rag_index_dir.resolve()
    units_dir = units_dir.resolve()

    need_units, need_mydata, reason = need_indexing(rag_index_dir, units_dir)
    result["need_index"] = need_units or need_mydata
    if not result["need_index"]:
        result["ok"] = True
        result["message"] = reason
        return result

    try:
        from rag.indexer import RAGIndex
    except ImportError:
        result["error"] = "RAG deps missing (pip install -r requirements-rag.txt)"
        result["message"] = result["error"]
        return result

    model = (embedding_model or "sentence-transformers/all-MiniLM-L6-v2").strip()
    try:
        index = RAGIndex(persist_dir=str(rag_index_dir), embedding_model=model)
    except Exception as e:
        result["error"] = str(e)[:80]
        result["message"] = result["error"]
        return result

    state = load_state(rag_index_dir)
    units_n = 0
    mydata_n = 0
    details_parts: list[str] = []

    # Units
    if units_dir.is_dir():
        current_u_hash = _folder_hash(units_dir, suffixes=RAG_DOC_SUFFIXES)
        if current_u_hash is not None and current_u_hash != state.get("units_hash"):
            saved_units_files = state.get("units_files")
            if isinstance(saved_units_files, dict):
                added, err = _index_folder_incremental(
                    index,
                    units_dir,
                    RAG_DOC_SUFFIXES,
                    None,
                    saved_units_files,
                    rag_index_dir,
                    folder_hash=current_u_hash,
                    save_units=True,
                )
                if err:
                    result["error"] = err
                    result["message"] = err
                    return result
                units_n = added
                if added:
                    details_parts.append(f"{added} units updated")
            else:
                paths_u = [
                    p for p in units_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in RAG_DOC_SUFFIXES
                ]
                if paths_u:
                    try:
                        units_n = index.add_documents_and_index([str(p) for p in paths_u])
                        save_state(
                            rag_index_dir,
                            units_hash=current_u_hash,
                            units_files=_compute_manifest(units_dir, suffixes=RAG_DOC_SUFFIXES),
                        )
                        details_parts.append(f"{units_n} units indexed")
                    except Exception as e:
                        result["error"] = str(e)[:80]
                        result["message"] = result["error"]
                        return result

    # Mydata (rag_index_dir as content root)
    mydata_root = rag_index_dir
    if mydata_root.is_dir():
        current_m_hash = _mydata_folder_hash(rag_index_dir)
        if current_m_hash is not None and current_m_hash != state.get("mydata_hash"):
            mydata_exclude_fn = _mydata_exclude(mydata_root)
            saved_mydata_files = state.get("mydata_files")
            if isinstance(saved_mydata_files, dict):
                added, err = _index_folder_incremental(
                    index,
                    mydata_root,
                    RAG_DOC_SUFFIXES | {RAG_WORKFLOW_SUFFIX},
                    mydata_exclude_fn,
                    saved_mydata_files,
                    rag_index_dir,
                    folder_hash=current_m_hash,
                    save_units=False,
                )
                if err:
                    result["error"] = err
                    result["message"] = err
                    result["units_count"] = units_n
                    return result
                mydata_n = added
                if added:
                    details_parts.append(f"{added} mydata updated")
            else:
                paths_m = [
                    p for p in mydata_root.rglob("*")
                    if p.is_file()
                    and (p.suffix.lower() in RAG_DOC_SUFFIXES or p.suffix.lower() == RAG_WORKFLOW_SUFFIX)
                    and not mydata_exclude_fn(p)
                ]
                if paths_m:
                    try:
                        mydata_n = index.add_documents_and_index([str(p) for p in paths_m])
                        save_state(
                            rag_index_dir,
                            mydata_hash=current_m_hash,
                            mydata_files=_compute_manifest(
                                mydata_root,
                                suffixes=RAG_DOC_SUFFIXES | {RAG_WORKFLOW_SUFFIX},
                                exclude_path=mydata_exclude_fn,
                            ),
                        )
                        details_parts.append(f"{mydata_n} mydata indexed")
                    except Exception as e:
                        result["error"] = str(e)[:80]
                        result["message"] = result["error"]
                        result["units_count"] = units_n
                        return result

    result["ok"] = True
    result["units_count"] = units_n
    result["mydata_count"] = mydata_n
    result["details"] = "; ".join(details_parts) if details_parts else "no changes"
    result["message"] = f"RAG: {result['details']}" if details_parts else "RAG: up to date"
    return result
