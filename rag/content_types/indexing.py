"""
RAG ``metadata.content_type`` for TaskVector repo-backed files (indexing / Chroma metadata).

Under ``assistants/roles`` and ``assistants/tools``: ``role_source``, ``role_readme``,
``tool_source``, ``tool_readme`` (every ``.md`` under those directories).

Under ``units/``: ``taskvector_units_source`` (``.py``), ``unit_readme`` for ``README.md``,
``taskvector_units_readme`` for other markdown.

Elsewhere: ``taskvector_<first_segment>_source`` for ``.py`` and plain-text suffixes;
``taskvector_<first_segment>_readme`` for other ``.md``. Binary types (PDF, etc.) → ``document``.
"""

from __future__ import annotations

import re
from pathlib import Path

_PLAIN_STYLE_SUFFIXES = frozenset(
    {
        ".csv",
        ".txt",
        ".yaml",
        ".yml",
        ".xml",
        ".log",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".tsv",
        ".rst",
    }
)


def sanitize_taskvector_token(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s or "repo"


def is_readme_md(filename: str) -> bool:
    return (filename or "").lower() == "readme.md"


def repo_relative_posix(repo_root: Path | None, abs_path: Path) -> str | None:
    if repo_root is None:
        return None
    try:
        return str(abs_path.resolve().relative_to(repo_root.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return None


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def content_type_for_markdown_file(
    path: Path,
    *,
    rag_units_dir: Path | None = None,
    rag_mydata_dir: Path | None = None,
) -> str:
    """
    Docling-backed markdown when only units/mydata roots are known (no full repo root).
    """
    pr = path.resolve()
    if rag_mydata_dir is not None and _path_is_under(pr, rag_mydata_dir.resolve()):
        return "document"
    if rag_units_dir is not None and _path_is_under(pr, rag_units_dir.resolve()):
        return "unit_readme" if is_readme_md(path.name) else "taskvector_units_readme"
    return "document"


def content_type_for_repo_relative_path(rel_posix: str, suffix: str) -> str:
    rel = (rel_posix or "").strip().lstrip("/").replace("\\", "/")
    if not rel:
        return "document"
    suf = (suffix or "").lower()
    parts = rel.split("/")
    token = sanitize_taskvector_token(parts[0] if parts else "repo")

    if rel.startswith("assistants/roles/"):
        if suf == ".py":
            return "role_source"
        if suf == ".md":
            return "role_readme"

    if rel.startswith("assistants/tools/"):
        if suf == ".py":
            return "tool_source"
        if suf == ".md":
            return "tool_readme"

    if rel.startswith("assistants/"):
        if suf == ".py":
            return "taskvector_assistants_source"
        if suf == ".md":
            return "taskvector_assistants_readme"

    if rel.startswith("units/"):
        base = Path(rel).name
        if suf == ".py":
            return "taskvector_units_source"
        if suf == ".md":
            return "unit_readme" if is_readme_md(base) else "taskvector_units_readme"

    if suf == ".py":
        return f"taskvector_{token}_source"
    if suf == ".md":
        return f"taskvector_{token}_readme"
    if suf in _PLAIN_STYLE_SUFFIXES:
        return f"taskvector_{token}_source"
    return "document"


def content_type_for_assistants_repo_relative(rel_posix: str, suffix: str) -> str:
    return content_type_for_repo_relative_path(rel_posix, suffix)


def content_type_for_indexed_file(
    repo_root: Path | None,
    abs_path: Path,
    *,
    suffix: str,
    fallback: str = "document",
) -> str:
    rel = repo_relative_posix(repo_root, abs_path)
    if rel is None:
        return fallback
    return content_type_for_repo_relative_path(rel, suffix)
