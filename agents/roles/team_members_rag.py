"""
Materialize agent **TeamMember** records for RAG: one ROLE.md per role under ``mydata/taskvector/<role_id>/ROLE.md``.
This never produces the combined agents_team_members.md file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List

from gui.components.settings.paths import RAG_SUBDIR


def roles_yaml_paths_sorted(roles_root: Path) -> List[Path]:
    """Sorted ``role.yaml`` paths under ``agents/roles/<id>/``."""
    if not roles_root.is_dir():
        return []
    return sorted(p.resolve() for p in roles_root.glob("*/role.yaml") if p.is_file())


def agents_roles_content_hash(roles_root: Path) -> str:
    """MD5 over relative path + raw bytes of each ``role.yaml`` (order-stable)."""
    paths = roles_yaml_paths_sorted(roles_root)
    if not paths:
        return hashlib.md5(b"").hexdigest()
    h = hashlib.md5()
    for p in paths:
        try:
            rel = p.relative_to(roles_root.resolve())
        except ValueError:
            rel = p.name
        h.update(str(rel).replace("\\", "/").encode("utf-8"))
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def _single_role_markdown(r) -> str:
    """Return the markdown content for one role."""
    resp = (r.responsibility_description or "").strip()
    header = f"# TaskVector AI agent Role Description: {r.id}\n\n"
    body = (
        f"## TeamMember: {r.id}\n"
        f"- **role_name**: {r.role_name}\n"
        f"- **name**: {r.name}\n"
        f"- **responsibility_description**: {resp}\n"
    )
    return header + body + "\n"


def materialize_team_members_rag_docs(
    mydata_dir: Path, *, roles_root: Path
) -> List[Path]:
    """
    Write one ``ROLE.md`` per role into ``mydata_dir/taskvector/<role_id>/ROLE.md`` from loaded role configs.
    Always returns list of written Paths (empty list if no roles). Does NOT write any combined file.
    """
    out_dir = (mydata_dir / RAG_SUBDIR).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not roles_root.is_dir():
        return []

    from agents.roles.registry import clear_role_cache, get_role, list_role_ids

    clear_role_cache()
    written: List[Path] = []
    for rid in sorted(list_role_ids()):
        try:
            r = get_role(rid)
        except Exception:
            continue
        role_dir = out_dir / r.id
        role_dir.mkdir(parents=True, exist_ok=True)
        out_path = role_dir / "ROLE.md"
        out_path.write_text(_single_role_markdown(r), encoding="utf-8")
        written.append(out_path)

    return written


# Keep a legacy-named wrapper that simply calls the per-role writer (for code expecting the old function).
def materialize_team_members_rag_doc(
    mydata_dir: Path, *, roles_root: Path
) -> List[Path]:
    """
    Backwards-compatible wrapper: returns the list of per-role files (does NOT create a combined file).
    """
    return materialize_team_members_rag_docs(mydata_dir, roles_root=roles_root)


__all__ = [
    "RAG_SUBDIR",
    "agents_roles_content_hash",
    "materialize_team_members_rag_doc",
    "materialize_team_members_rag_docs",
    "roles_yaml_paths_sorted",
]
