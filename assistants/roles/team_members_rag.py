"""
Materialize assistant **TeamMember** records for RAG: one markdown file under ``mydata/rag/`` so the
incremental index (``rag.context_updater.run_update``) ingests ``role_name``, ``name``, and
``responsibility_description`` for discovery and task delegation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


RAG_DOC_FILENAME = "assistants_team_members.md"
RAG_SUBDIR = "rag"


def roles_yaml_paths_sorted(roles_root: Path) -> list[Path]:
    """Sorted ``role.yaml`` paths under ``assistants/roles/<id>/``."""
    if not roles_root.is_dir():
        return []
    return sorted(p.resolve() for p in roles_root.glob("*/role.yaml") if p.is_file())


def assistants_roles_content_hash(roles_root: Path) -> str:
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


def materialize_team_members_rag_doc(mydata_dir: Path, *, roles_root: Path) -> Path:
    """
    Write ``mydata_dir/rag/assistants_team_members.md`` from loaded role configs.
    Call ``clear_role_cache()`` before ``get_role`` if YAML may have changed on disk.
    """
    out_dir = (mydata_dir / RAG_SUBDIR).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / RAG_DOC_FILENAME

    header = (
        "# TaskVector AI Assistant team members:\n\n"
    )

    if not roles_root.is_dir():
        out_path.write_text(
            header + "_No ``assistants/roles`` directory found; nothing to list._\n",
            encoding="utf-8",
        )
        return out_path

    from assistants.roles.registry import clear_role_cache, get_role, list_role_ids

    clear_role_cache()
    blocks: list[str] = []
    for rid in list_role_ids():
        try:
            r = get_role(rid)
        except Exception:
            continue
        resp = (r.responsibility_description or "").strip()
        blocks.append(
            f"## TeamMember: {r.id}\n"
            f"- **role_name**: {r.role_name}\n"
            f"- **name**: {r.name}\n"
            f"- **responsibility_description**: {resp}\n"
        )

    body = header + ("\n".join(blocks) if blocks else "_No roles with ``role.yaml`` found._\n")
    out_path.write_text(body, encoding="utf-8")
    return out_path


__all__ = [
    "RAG_DOC_FILENAME",
    "RAG_SUBDIR",
    "assistants_roles_content_hash",
    "materialize_team_members_rag_doc",
    "roles_yaml_paths_sorted",
]
