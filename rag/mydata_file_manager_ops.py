"""
Mydata file-manager domain logic: root organize, storage aggregates, directory listing, pie chart.

Used by ``MydataOrganize`` / ``MydataStorageReport`` units and by ``gui.components.rag_tab.helpers``
for pre-index organize (direct call, no workflow).
"""
from __future__ import annotations

import base64
import io
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from rag.context_updater import get_mydata_exclude_predicate
from rag.discriminant import classify_json_for_rag
from rag.extractors import load_workflow_json

MYDATA_ORGANIZED_SUBDIR = "_organized"


def human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit, div in (("KB", 1024), ("MB", 1024**2), ("GB", 1024**3)):
        if n < div * 1024:
            return f"{n / div:.1f} {unit}"
    return f"{n / 1024**3:.1f} TB"


def _json_layout_dest_dir(mydata: Path, raw_kind: str) -> Path:
    if raw_kind == "node_red":
        return mydata / "node-red" / "workflows"
    if raw_kind == "n8n":
        return mydata / "n8n" / "workflows"
    if raw_kind == "canonical":
        return mydata / "canonical" / "workflows"
    if raw_kind == "node_red_catalogue":
        return mydata / "node-red" / "nodes"
    if raw_kind == "chat_history":
        return mydata / MYDATA_ORGANIZED_SUBDIR / "Chat history"
    return mydata / MYDATA_ORGANIZED_SUBDIR / "JSON"


def storage_category_for_suffix(suffix: str) -> str:
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
    if s in {".txt", ".yaml", ".yml", ".xml", ".log", ".ini", ".cfg", ".conf", ".env", ".rst"}:
        return "Plain text"
    if s:
        return f"Other ({s})"
    return "No extension"


def has_mydata_root_organizable_files(mydata: Path) -> bool:
    """
    True if ``mydata`` has at least one regular file at its root that ``organize_mydata_root`` would act on
    (skips dotfiles and paths excluded by ``.noindex.txt`` / encrypted-name rules, same as organize).
    """
    if not mydata.is_dir():
        return False
    exclude = get_mydata_exclude_predicate(mydata)
    try:
        for path in mydata.iterdir():
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if exclude(path):
                continue
            return True
    except OSError:
        return False
    return False


def organize_mydata_root(mydata: Path) -> int:
    """
    Move root-level files under ``mydata`` into RAG layout (see module doc in gui rag_tab helpers).
    """
    if not mydata.is_dir():
        return 0
    if not has_mydata_root_organizable_files(mydata):
        return 0
    exclude = get_mydata_exclude_predicate(mydata)
    moved = 0
    try:
        for path in sorted(mydata.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file():
                continue
            name = path.name
            if name.startswith("."):
                continue
            if exclude(path):
                continue
            if path.suffix.lower() == ".json":
                data = load_workflow_json(path)
                raw = classify_json_for_rag(path, data) if data is not None else "generic"
                subdir = _json_layout_dest_dir(mydata, raw)
            else:
                label = storage_category_for_suffix(path.suffix)
                subdir = (mydata / MYDATA_ORGANIZED_SUBDIR) / label.replace("/", "-")
            subdir.mkdir(parents=True, exist_ok=True)
            dest = subdir / name
            if dest.resolve() == path.resolve():
                continue
            stem, suffix = dest.stem, dest.suffix
            counter = 0
            while (dest.exists() and dest.resolve() != path.resolve()) or exclude(dest):
                counter += 1
                if counter > 5000:
                    dest = path
                    break
                dest = subdir / f"{stem}_{counter}{suffix}"
            if counter > 5000 or dest.resolve() == path.resolve():
                continue
            try:
                shutil.move(str(path), str(dest))
                moved += 1
            except OSError:
                continue
    except OSError:
        return moved
    return moved


def chart_category_for_mydata_path(root: Path, p: Path, exclude: Callable[[Path], bool]) -> str | None:
    if exclude(p):
        return None
    try:
        rel = p.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    if parts[0] == "node-red" and len(parts) >= 2:
        return f"node-red/{parts[1]}"
    if parts[0] == "n8n" and len(parts) >= 2:
        return f"n8n/{parts[1]}"
    if parts[0] == "canonical" and len(parts) >= 2:
        return f"canonical/{parts[1]}"
    if parts[0] == "rag":
        return "rag/"
    if parts[0] == MYDATA_ORGANIZED_SUBDIR and len(parts) >= 2:
        return f"_organized/{parts[1]}"
    if parts[0] == MYDATA_ORGANIZED_SUBDIR:
        return "_organized"
    return storage_category_for_suffix(p.suffix)


def mydata_storage_by_category(mydata: Path) -> dict[str, tuple[int, int]]:
    root = mydata.resolve()
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    if not root.is_dir():
        return {}
    exclude = get_mydata_exclude_predicate(root)
    try:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.name.startswith("."):
                continue
            cat = chart_category_for_mydata_path(root, p, exclude)
            if cat is None:
                continue
            try:
                sz = p.stat().st_size
            except OSError:
                sz = 0
            out[cat][0] += 1
            out[cat][1] += sz
    except OSError:
        return {k: (v[0], v[1]) for k, v in out.items()}
    return {k: (v[0], v[1]) for k, v in out.items()}


def merge_sizes_for_chart(by_cat: dict[str, tuple[int, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, (_n, nbytes) in by_cat.items():
        key = "Other" if label.startswith("Other (") else label
        out[key] = out.get(key, 0) + nbytes
    return out


def pie_chart_data_uri(by_bytes: dict[str, int]) -> str | None:
    if not by_bytes or sum(by_bytes.values()) <= 0:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = list(by_bytes.keys())
    sizes = [float(by_bytes[k]) for k in labels]
    fig, ax = plt.subplots(figsize=(3.6, 2.9), dpi=90, facecolor="#1e1e1e")
    ax.set_facecolor("#1e1e1e")
    colors = [plt.cm.tab10(i % 10) for i in range(len(labels))]  # type: ignore[attr-defined]
    _wedges, _texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 6 else "",
        startangle=90,
        colors=colors,
        textprops={"fontsize": 8, "color": "#e8e8e8"},
    )
    for t in autotexts:
        t.set_color("#1a1a1a")
        t.set_fontsize(8)
    ax.axis("equal")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="#1e1e1e")
    plt.close(fig)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def build_mydata_storage_report(mydata: Path) -> dict[str, Any]:
    """Summary text + pie data URI from full-tree scan (respects noindex)."""
    root = mydata.resolve()
    by_cat = mydata_storage_by_category(root)
    total_files = sum(n for n, _b in by_cat.values())
    total_bytes = sum(b for _n, b in by_cat.values())
    lines = [
        f"{total_files} files · {human_bytes(total_bytes)} under mydata",
        "",
        f"Root-level files are auto-placed into node-red/, n8n/, canonical/, or "
        f"{MYDATA_ORGANIZED_SUBDIR}/ per rules above; .noindex.txt blocks moves and listing.",
        "",
    ]
    for label in sorted(by_cat.keys(), key=lambda k: (-by_cat[k][1], k)):
        n, b = by_cat[label]
        lines.append(f"· {label}: {n} file(s) — {human_bytes(b)}")
    summary_text = "\n".join(lines) if by_cat else "\n".join(lines[:4]) + "\n(no files)"
    merged = merge_sizes_for_chart(by_cat)
    pie_src = pie_chart_data_uri(merged)
    return {"summary_text": summary_text, "pie_src": pie_src}


def list_mydata_directory_entries(mydata: Path, rel_parts: list[str]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    """
    List one directory level under ``mydata``.

    Returns ``(rel_parts_effective, entries, errors)`` where each entry is
    ``{name, is_dir, size, rel}`` (``size`` is int or None for dirs).
    """
    errors: list[str] = []
    root = mydata.resolve()
    if not root.exists():
        return ([], [], [])
    rel_eff = [str(p) for p in rel_parts if str(p) and str(p) != "."]
    exclude = get_mydata_exclude_predicate(root)
    cur = root.joinpath(*rel_eff) if rel_eff else root
    if not cur.exists() or not cur.is_dir():
        rel_eff = []
        cur = root
    elif rel_eff and cur.resolve() != root.resolve() and exclude(cur):
        rel_eff = []
        cur = root

    entries: list[dict[str, Any]] = []
    try:
        for p in sorted(cur.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            if exclude(p):
                continue
            sz: int | None = None
            if p.is_file():
                try:
                    sz = p.stat().st_size
                except OSError:
                    sz = None
            try:
                rel_str = str(p.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel_str = p.name
            entries.append({"name": p.name, "is_dir": p.is_dir(), "size": sz, "rel": rel_str})
    except OSError as ex:
        errors.append(str(ex))
    return (rel_eff, entries, errors)


def build_mydata_listing_view_model(mydata: Path, rel_parts: list[str]) -> dict[str, Any]:
    """One directory level for the file-manager UI (no full-tree scan or chart)."""
    rel_eff, entries, list_errors = list_mydata_directory_entries(mydata, rel_parts)
    return {
        "rel_parts_effective": rel_eff,
        "entries": entries,
        "list_errors": list_errors,
    }


def build_mydata_refresh_view_model(mydata: Path, rel_parts: list[str]) -> dict[str, Any]:
    """Combined payload for the file-manager UI (listing + storage report)."""
    out = build_mydata_listing_view_model(mydata, rel_parts)
    report = build_mydata_storage_report(mydata)
    out["summary_text"] = report["summary_text"]
    out["pie_src"] = report["pie_src"]
    return out
