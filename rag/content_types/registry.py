"""
RAG content-type registry: discover packages under ``rag/content_types/<id>/`` with ``content_type.yaml``.

Includes **JSON classification** via each package’s ``discriminant.py`` (:func:`classify_json_for_rag`).

Used for mydata organize destinations, upload-pipeline routing, workflow paths, and RagDetectOrigin.
Repo-relative indexing labels remain in :mod:`rag.content_types.indexing` (separate concern).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, cast

import yaml

MYDATA_ORGANIZED_SUBDIR = "_organized"


@dataclass(frozen=True)
class ContentTypePackage:
    """One installed content-type package (directory + parsed ``content_type.yaml``)."""

    id: str
    directory: Path
    config: dict[str, Any]

    def path_relative_to_repo(self, *parts: str) -> Path:
        return self.directory.joinpath(*parts)

    def constants(self) -> dict[str, Any]:
        raw = self.config.get("constants")
        return dict(raw) if isinstance(raw, dict) else {}

    def extraction_workflow_filename(self) -> str | None:
        w = self.config.get("workflows")
        if not isinstance(w, dict):
            return None
        name = w.get("extraction")
        return str(name).strip() if name else None

    def extraction_workflow_path(self) -> Path | None:
        fn = self.extraction_workflow_filename()
        if not fn:
            return None
        p = (self.directory / fn).resolve()
        return p if p.is_file() else None


def _packages_root() -> Path:
    return Path(__file__).resolve().parent


def _iter_package_dirs(root: Path):
    """Yield all directories containing a ``content_type.yaml``, up to one sub-level deep.

    Allows grouping related content types under a shared folder (e.g. ``json/``) without
    requiring changes to individual package internals.
    """
    try:
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if (
                not child.is_dir()
                or child.name.startswith("_")
                or child.name.startswith(".")
            ):
                continue
            if (child / "content_type.yaml").is_file():
                yield child
            else:
                # One level deeper (e.g. json/json-generic/)
                try:
                    for grandchild in sorted(
                        child.iterdir(), key=lambda p: p.name.lower()
                    ):
                        if (
                            not grandchild.is_dir()
                            or grandchild.name.startswith("_")
                            or grandchild.name.startswith(".")
                        ):
                            continue
                        if (grandchild / "content_type.yaml").is_file():
                            yield grandchild
                except OSError:
                    pass
    except OSError:
        pass


def _load_package(dir_path: Path) -> ContentTypePackage | None:
    yml = dir_path / "content_type.yaml"
    if not yml.is_file():
        return None
    try:
        raw = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    cid = str(raw.get("id") or dir_path.name).strip()
    if not cid:
        cid = dir_path.name
    return ContentTypePackage(id=cid, directory=dir_path, config={**raw, "id": cid})


@lru_cache(maxsize=1)
def _discriminant_chain() -> tuple[tuple[str, Callable[[Path, Any], bool]], ...]:
    """(json_kind, matches) pairs in ascending PRIORITY order."""
    root = _packages_root()
    found: list[tuple[int, str, str, Callable[[Path, Any], bool]]] = []
    for child in _iter_package_dirs(root):
        mod_path = child / "discriminant.py"
        if not mod_path.is_file():
            continue
        mod_name = f"rag_content_types_disc_{child.name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(mod_name, mod_path)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        jk = getattr(mod, "JSON_KIND", None)
        fn = getattr(mod, "matches", None)
        if not jk or not callable(fn):
            continue
        pr = int(getattr(mod, "PRIORITY", 100))
        found.append(
            (pr, child.name, str(jk).strip(), cast(Callable[[Path, Any], bool], fn))
        )
    found.sort(key=lambda t: (t[0], t[1]))
    return tuple((jk, fn) for _pr, _dir, jk, fn in found)


def classify_json_for_rag(path: Path, data: dict | list | None) -> str:
    """
    Return ``json_kind`` for JSON ``data`` using each package’s ``discriminant.py`` (registry order).

    ``path`` is passed to ``matches`` for future path-based rules.
    """
    if data is None or not isinstance(data, (dict, list)):
        return "generic"
    for jk, matches in _discriminant_chain():
        try:
            if matches(path, data):
                return jk
        except Exception:
            continue
    return "generic"


@lru_cache(maxsize=1)
def list_packages() -> tuple[ContentTypePackage, ...]:
    root = _packages_root()
    out: list[ContentTypePackage] = []
    for child in _iter_package_dirs(root):
        pkg = _load_package(child)
        if pkg is not None:
            out.append(pkg)
    return tuple(out)


def refresh_registry() -> None:
    """Clear cached package discovery and discriminant modules (e.g. tests or hot-reload)."""
    list_packages.cache_clear()
    _discriminant_chain.cache_clear()


def get_package(content_type_id: str) -> ContentTypePackage | None:
    key = (content_type_id or "").strip()
    for p in list_packages():
        if p.id == key:
            return p
    return None


def _normalize_suffix(suffix: str) -> str:
    s = (suffix or "").strip().lower()
    return s if s.startswith(".") else (f".{s}" if s else "")


def package_for_json_kind(kind: str) -> ContentTypePackage | None:
    k = (kind or "").strip()
    for p in list_packages():
        detect = p.config.get("detect")
        if not isinstance(detect, dict):
            continue
        if str(detect.get("json_kind") or "").strip() == k:
            return p
    return None


def package_for_suffix(suffix: str) -> ContentTypePackage | None:
    suf = _normalize_suffix(suffix)
    if not suf:
        return None
    for p in list_packages():
        detect = p.config.get("detect")
        if not isinstance(detect, dict):
            continue
        for item in detect.get("suffixes") or []:
            if _normalize_suffix(str(item)) == suf:
                return p
    return None


def mydata_subdir_for_json_kind(kind: str) -> Path | None:
    pkg = package_for_json_kind(kind)
    if pkg is None:
        return None
    mo = pkg.config.get("mydata_organize")
    if not isinstance(mo, dict):
        return None
    sub = str(mo.get("subdir") or "").strip().replace("\\", "/")
    return Path(sub) if sub else None


def mydata_subdir_for_suffix(suffix: str) -> Path | None:
    pkg = package_for_suffix(suffix)
    if pkg is None:
        return None
    mo = pkg.config.get("mydata_organize")
    if not isinstance(mo, dict):
        return None
    sub = str(mo.get("subdir") or "").strip().replace("\\", "/")
    return Path(sub) if sub else None


def mydata_destination(
    mydata: Path, *, json_kind: str | None = None, suffix: str | None = None
) -> Path:
    """
    Resolve destination directory under ``mydata`` for root-level organize.

    When ``json_kind`` is set (from :func:`classify_json_for_rag`), use registry
    ``detect.json_kind`` + ``mydata_organize.subdir``. Otherwise use ``suffix`` for
    ``detect.suffixes`` matches, then fall back to :func:`storage_category_for_suffix` under
    ``_organized/<label>``.
    """
    root = mydata.resolve()
    if json_kind is not None:
        rel = mydata_subdir_for_json_kind(json_kind)
        if rel is not None:
            return root / rel
        rel_generic = mydata_subdir_for_json_kind("generic")
        if rel_generic is not None:
            return root / rel_generic
        return root / MYDATA_ORGANIZED_SUBDIR / "JSON"
    rel = mydata_subdir_for_suffix(suffix or "")
    if rel is not None:
        return root / rel
    label = storage_category_for_suffix(suffix or "")
    return root / MYDATA_ORGANIZED_SUBDIR / label.replace("/", "-")


def storage_category_for_suffix(suffix: str) -> str:
    """Label used for pie chart / fallback folder when no registry package matches."""
    s = (suffix or "").lower()
    if s == ".pdf":
        return "PDF"
    if s in {".doc", ".docx"}:
        return "Word"
    if s in {".xlsx", ".xls", ".csv", ".tsv"}:
        return "Spreadsheets"
    if s in {".pptx", ".ppt"}:
        return "Presentations"
    if s == ".html":
        return "HTML"
    if s == ".md":
        return "Markdown"
    if s == ".json":
        return "JSON"
    if s in {
        ".txt",
        ".yaml",
        ".yml",
        ".xml",
        ".log",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".rst",
    }:
        return "Plain text"
    if s:
        return f"Other ({s})"
    return "No extension"


def upload_router_payload(
    *,
    file_path: str = "",
    parsed_json: dict | list | None = None,
) -> dict[str, Any]:
    """
    Build a router dict from a **file path** and optional in-memory ``parsed_json``.

    ``file_path`` is stored on the result **as given** (no ``resolve()``). JSON is **not** read from
    disk here: ``parsed`` is only set when ``parsed_json`` is provided. For ``.json`` paths without
    in-memory JSON, ``json_kind`` / ``content_type_id`` are generic; parsing and kind inference happen
    in the type subflow (e.g. :class:`units.rag.rag_json_index_extract.RagJsonIndexExtract`).
    """
    fp = str(file_path or "").strip()
    out: dict[str, Any] = {
        "file_path": fp,
        "suffix": "",
        "parsed": None,
        "json_kind": "",
        "content_type_id": "",
    }
    path = Path(fp or ".")
    suf = path.suffix
    user_parsed = parsed_json if isinstance(parsed_json, (dict, list)) else None

    if suf.lower() == ".json":
        if user_parsed is not None:
            kind = classify_json_for_rag(path, user_parsed)
            out["json_kind"] = kind
            pkg = package_for_json_kind(kind) or package_for_json_kind("generic")
            out["content_type_id"] = pkg.id if pkg else "json-generic"
        else:
            out["json_kind"] = "generic"
            pkg = package_for_json_kind("generic")
            out["content_type_id"] = pkg.id if pkg else "json-generic"
    else:
        pkg = package_for_suffix(suf)
        out["content_type_id"] = pkg.id if pkg else "unknown-file"
        out.setdefault("json_kind", "")

    if not str(out.get("suffix") or "").strip():
        out["suffix"] = suf

    if user_parsed is not None:
        out["parsed"] = user_parsed

    return out


__all__ = [
    "MYDATA_ORGANIZED_SUBDIR",
    "ContentTypePackage",
    "classify_json_for_rag",
    "refresh_registry",
    "list_packages",
    "get_package",
    "package_for_json_kind",
    "package_for_suffix",
    "mydata_subdir_for_json_kind",
    "mydata_subdir_for_suffix",
    "mydata_destination",
    "storage_category_for_suffix",
    "upload_router_payload",
]
