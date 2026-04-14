"""
RAG index version control: manifests, MD5 hashes, incremental update of units/ and mydata/.
Used by the Flet app at startup and by `python -m rag update`.

Before indexing, when assistant role YAML or mydata/units triggers an update, a **TeamMember**
markdown file is written to ``mydata/rag/assistants_team_members.md`` (from ``assistants/roles/*/role.yaml``:
``role_name``, ``name``, ``responsibility_description``) so RAG can answer discovery and delegation queries.

Units tree: indexed suffixes are RAG_UNITS_INDEX_SUFFIXES (docs + .py). Exclusions come from
units/.noindex.txt (same rules as mydata). Encrypted-looking doc names are still excluded.

No-index files: mydata/.noindex.txt and units/.noindex.txt list paths to skip (one file per root).
Rules are relative to that root directory. Allowed:
  - Path prefix: e.g. "node-red/private" — excludes that path and any path under it (rel == prefix or rel.startswith(prefix + "/")).
  - Glob: any line containing * or ? is a glob pattern. If the line contains "**", it is matched with
    pathlib.PurePosixPath.match (recursive segments). Otherwise fnmatch is used on the relative path;
    fnmatch "*" and "?" do not match "/", so "*/test/*" is one segment on each side of "test", not arbitrary depth.
Lines starting with # are comments; blank lines are ignored. Backslashes are normalized to /.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable

Manifest = dict[str, str]

RAG_DOC_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
# Under units_dir only: documents plus Python sources (plain text in RAG, not Docling).
RAG_UNITS_INDEX_SUFFIXES = RAG_DOC_SUFFIXES | {".py"}
# Plain-text formats (read as UTF-8, no Docling): indexed from mydata and units
RAG_PLAIN_TEXT_SUFFIXES = {".csv", ".txt", ".yaml", ".yml", ".xml", ".log", ".ini", ".cfg", ".conf", ".env", ".tsv", ".rst"}
RAG_WORKFLOW_SUFFIX = ".json"
RAG_INDEX_STATE_FILENAME = ".rag_index_state.json"


NOINDEX_FILENAME = ".noindex.txt"


def _skip_encrypted_path(path: Path) -> bool:
    """Exclude paths that look like encrypted documents (e.g. sample-encrypted.pdf)."""
    return "encrypted" in path.name.lower()


def _load_noindex_rules(index_root: Path) -> tuple[list[str], list[str]]:
    """
    Read index_root/.noindex.txt and parse rules (one file only).

    Returns (path_prefixes, glob_patterns). All rules are relative to index_root (e.g. mydata or units).
    - path_prefixes: exclude path if rel == prefix or rel.startswith(prefix + "/").
    - glob_patterns: exclude path if _glob_matches_rel(rel_str, pattern).
    """
    root = index_root.resolve()
    noindex_file = root / NOINDEX_FILENAME
    prefixes: list[str] = []
    globs: list[str] = []
    if not noindex_file.is_file():
        return (prefixes, globs)
    try:
        for raw in noindex_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip().replace("\\", "/").strip("/") or raw.strip()
            if not line or line.startswith("#"):
                continue
            if "*" in line or "?" in line:
                globs.append(line)
            else:
                prefixes.append(line)
    except OSError:
        pass
    return (prefixes, globs)


def _glob_matches_rel(rel_str: str, pattern: str) -> bool:
    """
    Match a POSIX relative path against a noindex glob. Patterns containing ** use
    PurePosixPath.match; others use fnmatch (same as historical mydata behavior).
    """
    if "**" in pattern:
        try:
            return PurePosixPath(rel_str).match(pattern)
        except (ValueError, OSError):
            return False
    return fnmatch.fnmatch(rel_str, pattern)


def _path_matches_noindex_rules(
    path: Path,
    root: Path,
    path_prefixes: list[str],
    glob_patterns: list[str],
) -> bool:
    """True if path (under root) is excluded by any rule. rel = path relative to root."""
    try:
        rel = path.resolve().relative_to(root.resolve())
        rel_str = str(rel).replace("\\", "/")
    except (ValueError, OSError):
        return False
    for prefix in path_prefixes:
        if rel_str == prefix or rel_str.startswith(prefix + "/"):
            return True
    for pattern in glob_patterns:
        if _glob_matches_rel(rel_str, pattern):
            return True
    return False


def _units_exclude_path(units_dir: Path) -> Callable[[Path], bool]:
    """Exclude paths listed in units/.noindex.txt and _skip_encrypted_path for document-like names."""
    root = units_dir.resolve()
    path_prefixes, glob_patterns = _load_noindex_rules(units_dir)

    def _exclude(p: Path) -> bool:
        return _skip_encrypted_path(p) or _path_matches_noindex_rules(
            p, root, path_prefixes, glob_patterns
        )

    return _exclude


def _mydata_exclude_path(mydata_dir: Path) -> Callable[[Path], bool]:
    """Exclude encrypted paths and paths/files listed in mydata/.noindex.txt."""
    root = mydata_dir.resolve()
    path_prefixes, glob_patterns = _load_noindex_rules(mydata_dir)

    def _exclude(p: Path) -> bool:
        return _skip_encrypted_path(p) or _path_matches_noindex_rules(
            p, root, path_prefixes, glob_patterns
        )

    return _exclude


def get_mydata_exclude_predicate(mydata_dir: Path) -> Callable[[Path], bool]:
    """
    Same path predicate as RAG uses for mydata (``.noindex.txt`` + encrypted-looking names).

    Intended for the GUI file manager and auto-organize so exclusions stay aligned with indexing.
    """
    return _mydata_exclude_path(mydata_dir)


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
        return hashlib.md5(b"").hexdigest()
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


def _mydata_folder_hash(mydata_dir: Path) -> str | None:
    """MD5 of RAG-relevant files under mydata_dir. Excludes encrypted docs and dirs with .noindex.txt."""
    root = mydata_dir.resolve()
    if not root.is_dir():
        return None
    return _folder_hash(
        root,
        suffixes=RAG_DOC_SUFFIXES | RAG_PLAIN_TEXT_SUFFIXES | {RAG_WORKFLOW_SUFFIX},
        exclude_path=_mydata_exclude_path(mydata_dir),
    )


def load_state(rag_index_data_dir: Path) -> dict:
    """Return state from .rag_index_state.json. Keys: units_hash, mydata_hash, units_files, mydata_files, roles_rag_hash."""
    out: dict = {
        "units_hash": None,
        "mydata_hash": None,
        "units_files": None,
        "mydata_files": None,
        "roles_rag_hash": None,
    }
    state_path = rag_index_data_dir.resolve() / RAG_INDEX_STATE_FILENAME
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
    rag_index_data_dir: Path,
    *,
    units_hash: str | None = None,
    mydata_hash: str | None = None,
    units_files: Manifest | None = None,
    mydata_files: Manifest | None = None,
    roles_rag_hash: str | None = None,
) -> None:
    """Merge and write state to .rag_index_state.json under rag_index_data_dir."""
    state_path = (rag_index_data_dir / RAG_INDEX_STATE_FILENAME).resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    current = load_state(rag_index_data_dir)
    if units_hash is not None:
        current["units_hash"] = units_hash
    if mydata_hash is not None:
        current["mydata_hash"] = mydata_hash
    if units_files is not None:
        current["units_files"] = units_files
    if mydata_files is not None:
        current["mydata_files"] = mydata_files
    if roles_rag_hash is not None:
        current["roles_rag_hash"] = roles_rag_hash
    state_path.write_text(
        json.dumps(
            {
                "units_hash": current["units_hash"],
                "mydata_hash": current["mydata_hash"],
                "units_files": current.get("units_files"),
                "mydata_files": current.get("mydata_files"),
                "roles_rag_hash": current.get("roles_rag_hash"),
            },
            indent=0,
        ),
        encoding="utf-8",
    )


def need_indexing(rag_index_data_dir: Path, units_dir: Path, mydata_dir: Path) -> tuple[bool, bool, bool, str]:
    """
    Quick check: (need_units, need_mydata, need_roles, message).
    ``need_roles`` is True when ``assistants/roles/*/role.yaml`` content changed vs ``roles_rag_hash`` (TeamMember RAG doc must refresh).
    """
    try:
        state = load_state(rag_index_data_dir)
    except Exception:
        return (True, True, True, "check failed, will try index")

    need_units = False
    need_mydata = False
    need_roles = False
    if units_dir.resolve().is_dir():
        units_ex = _units_exclude_path(units_dir)
        current_u = _folder_hash(
            units_dir,
            suffixes=RAG_UNITS_INDEX_SUFFIXES,
            exclude_path=units_ex,
        )
        if current_u is not None and current_u != state.get("units_hash"):
            need_units = True
    if mydata_dir.resolve().is_dir():
        current_m = _mydata_folder_hash(mydata_dir)
        if current_m is not None and current_m != state.get("mydata_hash"):
            need_mydata = True

    try:
        from assistants.roles.registry import roles_definitions_dir
        from assistants.roles.team_members_rag import assistants_roles_content_hash

        roles_h = assistants_roles_content_hash(roles_definitions_dir())
        if roles_h != state.get("roles_rag_hash"):
            need_roles = True
    except Exception:
        need_roles = True

    if not need_units and not need_mydata and not need_roles:
        return (False, False, False, "up to date")
    parts = []
    if need_units:
        parts.append("units")
    if need_mydata:
        parts.append("mydata")
    if need_roles:
        parts.append("assistant roles")
    return (need_units, need_mydata, need_roles, "changed: " + ", ".join(parts))


def _compute_folder_updates(
    root: Path,
    suffixes: set[str],
    exclude_path: Callable[[Path], bool] | None,
    saved_manifest: Manifest | None,
) -> tuple[list[str], list[str], Manifest]:
    """Return (paths_to_delete, paths_to_add, current_manifest) for incremental update. Does not call index."""
    current_manifest = _compute_manifest(root, suffixes=suffixes, exclude_path=exclude_path)
    saved = saved_manifest or {}
    to_remove = set(saved) - set(current_manifest)
    to_add = [rel for rel in current_manifest if current_manifest[rel] != saved.get(rel)]
    delete_abs = [str((root / rel).resolve()) for rel in (to_remove | set(to_add))]
    add_abs = [str((root / rel).resolve()) for rel in to_add]
    return (delete_abs, add_abs, current_manifest)


def _index_folder_incremental(
    index: Any,
    root: Path,
    suffixes: set[str],
    exclude_path: Callable[[Path], bool] | None,
    saved_manifest: Manifest | None,
    rag_index_data_dir: Path,
    *,
    folder_hash: str,
    save_units: bool,
) -> tuple[int, str | None]:
    """Index only changed/new files. Returns (count_added, error_message)."""
    current_manifest = _compute_manifest(root, suffixes=suffixes, exclude_path=exclude_path)
    if not current_manifest:
        # Persist empty manifest so state stays in sync (e.g. mydata with no RAG files)
        if save_units:
            save_state(rag_index_data_dir, units_hash=folder_hash, units_files=current_manifest)
        else:
            save_state(rag_index_data_dir, mydata_hash=folder_hash, mydata_files=current_manifest)
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
        added = index.add_documents_and_index(
            add_abs,
            unit_source_roots=[root] if save_units else None,
        )
    if save_units:
        save_state(rag_index_data_dir, units_hash=folder_hash, units_files=current_manifest)
    else:
        save_state(rag_index_data_dir, mydata_hash=folder_hash, mydata_files=current_manifest)
    return (added, None)


def run_update(
    rag_index_data_dir: Path,
    units_dir: Path,
    mydata_dir: Path,
    *,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    """
    Update RAG index from units_dir and mydata_dir when content has changed.
    chroma_db and .rag_index_state.json live in rag_index_data_dir; mydata content is in mydata_dir.
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
    rag_index_data_dir = rag_index_data_dir.resolve()
    units_dir = units_dir.resolve()
    mydata_dir = mydata_dir.resolve()

    need_units, need_mydata, need_roles, reason = need_indexing(rag_index_data_dir, units_dir, mydata_dir)
    result["need_index"] = need_units or need_mydata or need_roles
    if not result["need_index"]:
        result["ok"] = True
        result["message"] = reason
        print("RAG: Up to date.", flush=True)
        return result

    print(f"RAG: {reason}", flush=True)

    try:
        from assistants.roles.registry import roles_definitions_dir
        from assistants.roles.team_members_rag import materialize_team_members_rag_doc

        roles_root = roles_definitions_dir()
        if need_units or need_mydata or need_roles:
            materialize_team_members_rag_doc(mydata_dir, roles_root=roles_root)
    except Exception as e:
        result["error"] = f"team members RAG doc: {str(e)[:80]}"
        result["message"] = result["error"]
        return result

    effective_need_mydata = need_mydata or need_roles
    try:
        from rag.indexer import RAGIndex, _default_rag_embedding_model
    except ImportError:
        result["error"] = "RAG deps missing (pip install -r requirements-rag.txt)"
        result["message"] = result["error"]
        return result

    model = (embedding_model or _default_rag_embedding_model()).strip()
    try:
        index = RAGIndex(persist_dir=str(rag_index_data_dir), embedding_model=model)
    except Exception as e:
        result["error"] = str(e)[:80]
        result["message"] = result["error"]
        return result

    state = load_state(rag_index_data_dir)
    all_delete: list[str] = []
    all_add: list[str] = []
    units_add_count = 0
    mydata_add_count = 0
    units_hash_save: str | None = None
    units_manifest_save: Manifest | None = None
    mydata_hash_save: str | None = None
    mydata_manifest_save: Manifest | None = None
    details_parts: list[str] = []

    # Collect all paths to delete and add from units and mydata (one indexing run later)
    if need_units and units_dir.is_dir():
        units_ex = _units_exclude_path(units_dir)
        current_u_hash = _folder_hash(
            units_dir,
            suffixes=RAG_UNITS_INDEX_SUFFIXES,
            exclude_path=units_ex,
        )
        saved_units_files = state.get("units_files")
        if isinstance(saved_units_files, dict):
            del_u, add_u, manifest_u = _compute_folder_updates(
                units_dir,
                RAG_UNITS_INDEX_SUFFIXES,
                units_ex,
                saved_units_files,
            )
            all_delete.extend(del_u)
            all_add.extend(add_u)
            units_add_count = len(add_u)
            units_manifest_save = manifest_u
        else:
            paths_u = [
                p
                for p in units_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in RAG_UNITS_INDEX_SUFFIXES and not units_ex(p)
            ]
            path_strs_u = [str(p) for p in paths_u]
            all_add.extend(path_strs_u)
            units_add_count = len(path_strs_u)
            units_manifest_save = (
                _compute_manifest(
                    units_dir,
                    suffixes=RAG_UNITS_INDEX_SUFFIXES,
                    exclude_path=units_ex,
                )
                if paths_u
                else {}
            )
        units_hash_save = current_u_hash

    if effective_need_mydata and mydata_dir.is_dir():
        mydata_exclude = _mydata_exclude_path(mydata_dir)
        current_m_hash = _mydata_folder_hash(mydata_dir)
        saved_mydata_files = state.get("mydata_files")
        if isinstance(saved_mydata_files, dict):
            del_m, add_m, manifest_m = _compute_folder_updates(
                mydata_dir,
                RAG_DOC_SUFFIXES | RAG_PLAIN_TEXT_SUFFIXES | {RAG_WORKFLOW_SUFFIX},
                mydata_exclude,
                saved_mydata_files,
            )
            all_delete.extend(del_m)
            all_add.extend(add_m)
            mydata_add_count = len(add_m)
            mydata_manifest_save = manifest_m
        else:
            paths_m = [
                p for p in mydata_dir.rglob("*")
                if p.is_file()
                and (p.suffix.lower() in RAG_DOC_SUFFIXES or p.suffix.lower() in RAG_PLAIN_TEXT_SUFFIXES or p.suffix.lower() == RAG_WORKFLOW_SUFFIX)
                and not mydata_exclude(p)
            ]
            path_strs_m = [str(p) for p in paths_m]
            all_add.extend(path_strs_m)
            mydata_add_count = len(path_strs_m)
            mydata_manifest_save = (
                _compute_manifest(
                    mydata_dir,
                    suffixes=RAG_DOC_SUFFIXES | RAG_PLAIN_TEXT_SUFFIXES | {RAG_WORKFLOW_SUFFIX},
                    exclude_path=mydata_exclude,
                )
                if paths_m
                else {}
            )
        mydata_hash_save = current_m_hash

    # One delete + one add so we get a single "Applying transformations" / "Generating embeddings" run
    try:
        if all_delete:
            print(f"RAG: Removing {len(all_delete)} path(s) from index...", flush=True)
            index.delete_by_file_paths(all_delete)
        if all_add:
            print(f"RAG: Indexing {len(all_add)} document(s)...", flush=True)
            total_added = index.add_documents_and_index(
                all_add,
                unit_source_roots=[units_dir] if units_dir.is_dir() else None,
            )
            print(f"RAG: Done. {total_added} document(s) indexed.", flush=True)
            if units_add_count or mydata_add_count:
                details_parts.append(f"{total_added} indexed ({units_add_count} units, {mydata_add_count} mydata)")
    except Exception as e:
        result["error"] = str(e)[:80]
        result["message"] = result["error"]
        if mydata_hash_save is not None:
            save_state(rag_index_data_dir, mydata_hash=mydata_hash_save, mydata_files=mydata_manifest_save or {})
        return result

    units_n = units_add_count
    mydata_n = mydata_add_count

    roles_h_save: str | None = None
    try:
        from assistants.roles.registry import roles_definitions_dir
        from assistants.roles.team_members_rag import assistants_roles_content_hash

        roles_h_save = assistants_roles_content_hash(roles_definitions_dir())
    except Exception:
        pass

    if units_hash_save is not None:
        save_state(rag_index_data_dir, units_hash=units_hash_save, units_files=units_manifest_save or {})
    if mydata_hash_save is not None:
        save_state(rag_index_data_dir, mydata_hash=mydata_hash_save, mydata_files=mydata_manifest_save or {})
    if roles_h_save is not None:
        save_state(rag_index_data_dir, roles_rag_hash=roles_h_save)

    result["ok"] = True
    result["units_count"] = units_n
    result["mydata_count"] = mydata_n
    result["details"] = "; ".join(details_parts) if details_parts else "no changes"
    result["message"] = f"RAG: {result['details']}" if details_parts else "RAG: up to date"
    return result
