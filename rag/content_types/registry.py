"""
Generic RAG content-type registry.

Discovers packages under:

    rag/content_types/<family>/<content-type-id>/

Each package must contain:

    content_type.yaml

Optional:

    discriminant.py

Discriminants provide semantic classification via:

    CONTENT_KIND
    matches(path, data)

This registry is intentionally generic across:
- markdown
- plain-text
- json
- yaml
- xml
- future families

The registry itself does NOT care about serialization format semantics.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, cast

import yaml

MYDATA_ORGANIZED_SUBDIR = "_organized"


# ============================================================================
# Models
# ============================================================================


@dataclass(frozen=True)
class ContentTypePackage:
    """
    One installed content-type package.
    """

    id: str
    family: str
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


@dataclass(frozen=True)
class Discriminant:
    """
    Runtime semantic classifier.
    """

    family: str
    content_kind: str
    content_type_id: str
    matches: Callable[[Path, Any], bool]
    priority: int = 100


# ============================================================================
# Discovery
# ============================================================================


def _packages_root() -> Path:
    return Path(__file__).resolve().parent


def _iter_family_dirs(root: Path):
    try:
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if (
                not child.is_dir()
                or child.name.startswith("_")
                or child.name.startswith(".")
            ):
                continue

            yield child

    except OSError:
        return


def _iter_package_dirs(root: Path):
    """
    Yield:

        (family, package_dir)
    """

    for family_dir in _iter_family_dirs(root):
        family = family_dir.name

        try:
            for child in sorted(
                family_dir.iterdir(),
                key=lambda p: p.name.lower(),
            ):
                if (
                    not child.is_dir()
                    or child.name.startswith("_")
                    or child.name.startswith(".")
                ):
                    continue

                if (child / "content_type.yaml").is_file():
                    yield family, child

        except OSError:
            continue


def _load_package(
    family: str,
    dir_path: Path,
) -> ContentTypePackage | None:
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

    return ContentTypePackage(
        id=cid,
        family=family,
        directory=dir_path,
        config={
            **raw,
            "id": cid,
            "family": family,
        },
    )


# ============================================================================
# Discriminants
# ============================================================================


@lru_cache(maxsize=1)
def _discriminant_chain() -> tuple[Discriminant, ...]:
    """
    Runtime semantic classification chain.

    Ordered by:
    - PRIORITY
    - content_type_id
    """

    root = _packages_root()

    found: list[Discriminant] = []

    for family, child in _iter_package_dirs(root):
        mod_path = child / "discriminant.py"

        if not mod_path.is_file():
            continue

        pkg = _load_package(family, child)

        if pkg is None:
            continue

        mod_name = f"rag_content_types_disc_{family}_{child.name.replace('-', '_')}"

        spec = importlib.util.spec_from_file_location(
            mod_name,
            mod_path,
        )

        if spec is None or spec.loader is None:
            continue

        mod = importlib.util.module_from_spec(spec)

        spec.loader.exec_module(mod)

        content_kind = getattr(mod, "CONTENT_KIND", None)
        fn = getattr(mod, "matches", None)

        if not content_kind or not callable(fn):
            continue

        found.append(
            Discriminant(
                family=family,
                content_kind=str(content_kind).strip(),
                content_type_id=pkg.id,
                matches=cast(Callable[[Path, Any], bool], fn),
                priority=int(getattr(mod, "PRIORITY", 100)),
            )
        )

    found.sort(
        key=lambda d: (
            d.priority,
            d.content_type_id,
        )
    )

    return tuple(found)


# ============================================================================
# Public API
# ============================================================================


def classify_content(
    path: Path,
    data: Any = None,
) -> dict[str, str]:
    """
    Generic semantic content classification.

    Returns:

    {
        "family": "...",
        "content_kind": "...",
        "id": "...",
    }
    """

    for disc in _discriminant_chain():
        try:
            if disc.matches(path, data):
                return {
                    "family": disc.family,
                    "content_kind": disc.content_kind,
                    "id": disc.content_type_id,
                }

        except Exception:
            continue

    return {
        "family": "unknown",
        "content_kind": "unknown",
        "id": "unknown",
    }


@lru_cache(maxsize=1)
def list_packages() -> tuple[ContentTypePackage, ...]:
    root = _packages_root()

    out: list[ContentTypePackage] = []

    for family, child in _iter_package_dirs(root):
        pkg = _load_package(family, child)

        if pkg is not None:
            out.append(pkg)

    return tuple(out)


def refresh_registry() -> None:
    """
    Clear all cached registry state.
    """

    list_packages.cache_clear()
    _discriminant_chain.cache_clear()
    suffixes_for_strategy.cache_clear()


def get_package(content_type_id: str) -> ContentTypePackage | None:
    key = (content_type_id or "").strip()

    for p in list_packages():
        if p.id == key:
            return p

    return None


# ============================================================================
# Suffix Helpers
# ============================================================================


def _normalize_suffix(suffix: str) -> str:
    s = (suffix or "").strip().lower()

    return s if s.startswith(".") else (f".{s}" if s else "")


@lru_cache(maxsize=None)
def suffixes_for_strategy(strategy: str) -> frozenset[str]:
    found: set[str] = set()

    for pkg in list_packages():
        if str(pkg.config.get("index_strategy") or "").strip() != strategy:
            continue

        detect = pkg.config.get("detect") or {}

        for suf in detect.get("suffixes") or []:
            s = _normalize_suffix(str(suf))

            if s:
                found.add(s)

    return frozenset(found)


def package_for_content_kind(kind: str) -> ContentTypePackage | None:
    k = (kind or "").strip()

    for p in list_packages():
        detect = p.config.get("detect")

        if not isinstance(detect, dict):
            continue

        if str(detect.get("content_kind") or "").strip() == k:
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


# ============================================================================
# MyData Routing
# ============================================================================


def mydata_subdir_for_content_kind(kind: str) -> Path | None:
    pkg = package_for_content_kind(kind)

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
    mydata: Path,
    *,
    content_kind: str | None = None,
    suffix: str | None = None,
) -> Path:
    """
    Resolve destination directory under mydata.
    """

    root = mydata.resolve()

    if content_kind is not None:
        rel = mydata_subdir_for_content_kind(content_kind)

        if rel is not None:
            return root / rel

        rel_generic = mydata_subdir_for_content_kind("generic")

        if rel_generic is not None:
            return root / rel_generic

        return root / MYDATA_ORGANIZED_SUBDIR / "generic"

    rel = mydata_subdir_for_suffix(suffix or "")

    if rel is not None:
        return root / rel

    label = storage_category_for_suffix(suffix or "")

    return root / MYDATA_ORGANIZED_SUBDIR / label.replace("/", "-")


# ============================================================================
# Labels
# ============================================================================


def storage_category_for_suffix(suffix: str) -> str:
    suf = _normalize_suffix(suffix)

    if not suf:
        return "No extension"

    pkg = package_for_suffix(suf)

    if pkg is not None:
        title = str(pkg.config.get("title") or "").strip()

        return title if title else pkg.id

    return f"Other ({suf})"


# ============================================================================
# Upload Routing
# ============================================================================


def upload_router_payload(
    *,
    file_path: str = "",
    parsed_data: Any = None,
) -> dict[str, Any]:
    """
    Build generic upload router payload.
    """

    fp = str(file_path or "").strip()

    out: dict[str, Any] = {
        "file_path": fp,
        "suffix": "",
        "parsed": None,
        "family": "",
        "content_kind": "",
        "content_type_id": "",
    }

    path = Path(fp or ".")

    suf = path.suffix

    classification = classify_content(
        path=path,
        data=parsed_data,
    )

    out["family"] = classification["family"]
    out["content_kind"] = classification["content_kind"]
    out["content_type_id"] = classification["id"]

    if not out["content_type_id"]:
        pkg = package_for_suffix(suf)

        if pkg is not None:
            out["content_type_id"] = pkg.id
            out["family"] = pkg.family

    out["suffix"] = suf

    if parsed_data is not None:
        out["parsed"] = parsed_data

    return out


# ============================================================================
# Exports
# ============================================================================


__all__ = [
    "MYDATA_ORGANIZED_SUBDIR",
    "ContentTypePackage",
    "Discriminant",
    "classify_content",
    "refresh_registry",
    "list_packages",
    "get_package",
    "package_for_content_kind",
    "package_for_suffix",
    "suffixes_for_strategy",
    "mydata_subdir_for_content_kind",
    "mydata_subdir_for_suffix",
    "mydata_destination",
    "storage_category_for_suffix",
    "upload_router_payload",
]
