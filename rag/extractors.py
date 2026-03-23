"""
Extract searchable metadata from workflows (Node-RED, n8n) and node catalogues.
Accepts both string and parsed JSON (list/dict) for text fields (description, name, label, etc.).

Classification of JSON (workflow vs catalogue vs library) is in rag.discriminant.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _to_string(val: Any) -> str:
    """Normalize to string: keep str, convert list/dict to JSON string, else str()."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, dict)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def _to_string_list(val: Any) -> list[str]:
    """Normalize to list of strings (e.g. keywords, categories). Accepts list, single str, or dict/other."""
    if val is None:
        return []
    if isinstance(val, list):
        return [_to_string(x) for x in val if x is not None]
    if isinstance(val, str):
        return [val] if val.strip() else []
    return [_to_string(val)]


def extract_node_red_workflow_meta(raw: dict | list, source: str) -> dict[str, Any]:
    """Extract metadata from Node-RED flow JSON for indexing (raw flow or library wrapper with readme/summary)."""
    nodes: list[dict] = []
    if isinstance(raw, list):
        nodes = raw
    elif isinstance(raw, dict):
        nodes = raw.get("nodes") or raw.get("flow") or []
        if not nodes and raw.get("flows") and isinstance(raw["flows"], list) and raw["flows"]:
            first = raw["flows"][0]
            if isinstance(first, dict) and "nodes" in first:
                nodes = first["nodes"]
            elif isinstance(first, list):
                nodes = first

    unit_types: set[str] = set()
    labels: list[str] = []
    name = "Unknown"
    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = (n.get("type") or n.get("unitType") or n.get("processType") or "")
        if str(ntype).lower() == "tab":
            name = _to_string(n.get("label") or n.get("name") or name)
        if ntype:
            unit_types.add(str(ntype).split(".")[-1])
        lbl = n.get("label") or n.get("name")
        if lbl is not None and str(ntype).lower() != "tab":
            labels.append(_to_string(lbl))

    if isinstance(raw, dict):
        if name == "Unknown":
            tab = raw.get("flows", [{}])[0] if raw.get("flows") else raw
            if isinstance(tab, dict):
                name = _to_string(tab.get("label") or tab.get("name") or name)
        # Library wrapper or any flow with readme/summary: use for name and include in meta for search
        summary = _to_string(raw.get("summary") or "")
        readme = _to_string(raw.get("readme") or "")
        if summary or readme:
            if name == "Unknown" and summary:
                name = summary[:200] if len(summary) <= 200 else summary[:197] + "..."
            elif name == "Unknown" and readme:
                name = readme[:80].strip() if len(readme) <= 80 else readme[:77].strip() + "..."

    result: dict[str, Any] = {
        "content_type": "workflow",
        "format": "node_red",
        "name": name,
        "source": source,
        "unit_types": list(unit_types),
        "labels": labels[:20],
        "node_count": len([n for n in nodes if isinstance(n, dict) and n.get("type")]),
    }
    if isinstance(raw, dict):
        if raw.get("summary"):
            result["summary"] = _to_string(raw["summary"])[:500]
        if raw.get("readme"):
            result["readme"] = _to_string(raw["readme"])[:2000]
    return result


def extract_n8n_workflow_meta(raw: dict, source: str) -> dict[str, Any]:
    """Extract metadata from n8n workflow JSON for indexing."""
    nodes = raw.get("nodes") or []
    integrations: set[str] = set()
    labels: list[str] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = n.get("type") or ""
        if isinstance(ntype, str) and "." in ntype:
            integrations.add(ntype.split(".")[-1])
        name = n.get("name")
        if name is not None:
            labels.append(_to_string(name))

    # Prefer human-readable name for search; fall back to instanceId only when name is missing
    wf_name = _to_string(
        raw.get("name")
        or (isinstance(raw.get("meta"), dict) and raw["meta"].get("instanceId"))
        or "Unknown"
    )

    return {
        "content_type": "workflow",
        "format": "n8n",
        "name": wf_name,
        "source": source,
        "integrations": list(integrations),
        "labels": labels[:20],
        "node_count": len(nodes),
    }


def extract_canonical_workflow_meta(raw: dict, source: str) -> dict[str, Any]:
    """Extract metadata from canonical process graph JSON (ProcessGraph: units + connections) for indexing."""
    units = raw.get("units") or []
    unit_types: set[str] = set()
    labels: list[str] = []
    for u in units:
        if not isinstance(u, dict):
            continue
        utype = (u.get("type") or "").strip()
        if utype:
            unit_types.add(utype)
        uid = u.get("id")
        if uid is not None:
            labels.append(_to_string(uid))
    name = _to_string(raw.get("name") or "Canonical graph")
    return {
        "content_type": "workflow",
        "format": "canonical",
        "name": name,
        "source": source,
        "unit_types": list(unit_types),
        "labels": labels[:20],
        "node_count": len(units),
    }


def workflow_meta_to_text(meta: dict[str, Any]) -> str:
    """Convert workflow metadata to searchable text for embedding."""
    parts = [f"Workflow: {meta.get('name', '')}"]
    if meta.get("origin"):
        parts.append(f"Origin: {meta['origin']}")
    if meta.get("unit_types"):
        parts.append(f"Node types: {', '.join(meta['unit_types'])}")
    if meta.get("integrations"):
        parts.append(f"Integrations: {', '.join(meta['integrations'])}")
    if meta.get("labels"):
        parts.append(f"Nodes: {', '.join(meta['labels'][:10])}")
    if meta.get("summary"):
        parts.append(meta.get("summary", ""))
    if meta.get("readme"):
        parts.append((meta.get("readme") or "")[:500])
    parts.append(f"Format: {meta.get('format', '')}")
    return " | ".join(p for p in parts if p)


def extract_node_red_catalogue_module(module: dict, source: str = "node_red_catalogue") -> dict[str, Any]:
    """Extract metadata from one Node-RED catalogue module (npm package). description/keywords/etc. can be string or parsed JSON."""
    mid = _to_string(module.get("id") or "")
    desc = _to_string(module.get("description") or "")
    keywords = _to_string_list(module.get("keywords"))
    types_list = _to_string_list(module.get("types"))[:30]
    categories = _to_string_list(module.get("categories"))
    url = _to_string(module.get("url") or "")

    return {
        "content_type": "node",
        "format": "node_red",
        "id": mid,
        "name": mid,
        "source": source,
        "description": desc,
        "keywords": keywords,
        "node_types": types_list,
        "categories": categories,
        "url": url,
    }


def node_meta_to_text(meta: dict[str, Any]) -> str:
    """Convert node metadata to searchable text for embedding."""
    parts = [
        meta.get("name", ""),
        meta.get("description", ""),
        " ".join(meta.get("keywords", [])),
        " ".join(meta.get("categories", [])),
        " ".join(meta.get("node_types", [])[:15]),
    ]
    return " | ".join(p for p in parts if p)


def extract_chat_history_meta(raw: dict | list, source: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []

    if isinstance(raw, dict) and "messages" in raw:
        messages = raw.get("messages") or []
    elif isinstance(raw, list):
        messages = raw

    content_texts: list[str] = []
    roles: set[str] = set()
    feedbacks: list[str] = []
    assistants: set[str] = set()  # <-- collect assistant names
    timestamps: list[str] = []    # <-- collect timestamps

    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        msg_content = m.get("content")
        if role:
            roles.add(str(role))
        if msg_content:
            if isinstance(msg_content, list):
                content_texts.append(" ".join(_to_string(x) for x in msg_content))
            else:
                content_texts.append(_to_string(msg_content))
        # collect feedback if present
        fb = m.get("feedback")
        if fb:
            if isinstance(fb, dict):
                fb_text = " | ".join(f"{k}:{v}" for k, v in fb.items())
            else:
                fb_text = str(fb)
            feedbacks.append(fb_text)
        # collect assistant name if present
        assistant_name = m.get("assistant")
        if assistant_name:
            assistants.add(str(assistant_name))
        # collect timestamp if present
        ts = m.get("ts")
        if ts:
            timestamps.append(str(ts))

    name = f"Chat history ({len(messages)} messages)"

    return {
        "content_type": "chat_history",
        "format": "chat_history",
        "name": name,
        "source": source,
        "roles": list(roles),
        "messages_count": len(messages),
        "text": " | ".join(content_texts[:1000]),  # keep first 1000 messages for indexing
        "feedbacks": feedbacks,
        "assistants": list(assistants),  # new field
        "timestamps": timestamps,         # new field
    }


def chat_history_meta_to_text(meta: dict[str, Any]) -> str:
    """
    Convert chat history metadata to searchable text for embedding.
    
    Uses the messages' content and roles.
    """
    parts: list[str] = [f"Chat history: {meta.get('name', '')}"]
    
    if meta.get("roles"):
        parts.append(f"Roles: {', '.join(meta['roles'])}")
    
    if meta.get("messages_count") is not None:
        parts.append(f"Messages count: {meta['messages_count']}")
    
    if meta.get("text"):
        # truncate to avoid overly long embeddings if needed
        text_content = meta["text"]
        if len(text_content) > 2000:
            text_content = text_content[:1997] + "..."
        parts.append(text_content)
    
    parts.append(f"Format: {meta.get('format', '')}")
    
    return " | ".join(p for p in parts if p)


# Indexing: include a large transcript; chunk so each vector stays bounded (Chroma + embedders).
CHAT_HISTORY_INDEX_MAX_MESSAGES = 8000
CHAT_HISTORY_INDEX_CHUNK_CHARS = 4000


def _chat_history_message_dicts(raw: dict | list) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and "messages" in raw:
        messages = raw.get("messages") or []
    elif isinstance(raw, list):
        messages = raw
    else:
        return []
    if not isinstance(messages, list):
        return []
    return [m for m in messages if isinstance(m, dict)]


def _slim_chat_meta_for_index(meta: dict[str, Any]) -> dict[str, Any]:
    """Vector-store metadata only (full transcript is in Document.text, not meta)."""
    keys = (
        "content_type",
        "format",
        "name",
        "source",
        "messages_count",
        "roles",
        "assistants",
    )
    slim: dict[str, Any] = {k: meta[k] for k in keys if k in meta}
    fb = meta.get("feedbacks")
    if fb:
        slim["feedbacks"] = fb[:40] if isinstance(fb, list) and len(fb) > 40 else fb
    ts = meta.get("timestamps")
    if ts:
        slim["timestamps"] = ts[:80] if isinstance(ts, list) and len(ts) > 80 else ts
    return slim


def build_chat_history_index_documents(
    raw: dict | list,
    *,
    source: str,
    file_path: str,
    max_messages: int = CHAT_HISTORY_INDEX_MAX_MESSAGES,
    chunk_chars: int = CHAT_HISTORY_INDEX_CHUNK_CHARS,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Build (text, metadata) pairs for vector indexing.

    Splits long chats into multiple chunks so mid-conversation content is retrievable.
    Metadata is slim (no full concatenated text field) so Chroma limits are respected.
    """
    messages = _chat_history_message_dicts(raw)[:max_messages]
    lines: list[str] = []
    for m in messages:
        role = str(m.get("role") or "?").strip()
        msg_content = m.get("content")
        if msg_content is None:
            body = ""
        elif isinstance(msg_content, list):
            body = " ".join(_to_string(x) for x in msg_content)
        else:
            body = _to_string(msg_content)
        body = body.strip()
        extras: list[str] = []
        fb = m.get("feedback")
        if fb:
            extras.append(f"feedback={_to_string(fb)}")
        an = m.get("assistant")
        if an:
            extras.append(f"assistant={_to_string(an)}")
        ts = m.get("ts")
        if ts:
            extras.append(f"ts={_to_string(ts)}")
        suffix = (" | " + " ".join(extras)) if extras else ""
        line = f"{role}: {body}{suffix}".rstrip() if (body or suffix) else (f"{role}:" if role else "")
        if line:
            lines.append(line)

    if not lines:
        return []

    summary = extract_chat_history_meta(raw, source=source)
    slim = _slim_chat_meta_for_index(summary)
    slim["file_path"] = file_path
    slim["raw_json_path"] = file_path
    slim["origin"] = "chat_history"

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    sep = 1  # newline between lines

    for line in lines:
        if len(line) > chunk_chars:
            if buf:
                chunks.append("\n".join(buf))
                buf = []
                buf_len = 0
            chunks.append(line)
            continue
        add = len(line) + (sep if buf else 0)
        if buf and buf_len + add > chunk_chars:
            chunks.append("\n".join(buf))
            buf = [line]
            buf_len = len(line)
        else:
            buf.append(line)
            buf_len += add

    if buf:
        chunks.append("\n".join(buf))

    n = len(chunks)
    out: list[tuple[str, dict[str, Any]]] = []
    for i, chunk in enumerate(chunks):
        meta = {**slim, "chunk_index": i, "chunk_count": n}
        header = (
            f"{summary.get('name', 'Chat history')} — excerpt {i + 1} of {n} "
            f"(source: {source})\n\n"
        )
        out.append((header + chunk, meta))
    return out


def load_workflow_json(path: Path) -> dict | list | None:
    """Load workflow JSON from file. Classify with rag.discriminant.classify_json_for_rag after load."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
    except Exception:
        return None

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "nodes" in data and "connections" in data:
            return data  # n8n
        if "nodes" in data or "flows" in data or any(
            isinstance(v, list) and v and isinstance(v[0], dict)
            for v in (data.get("flows"), data.get("nodes"))
        ):
            return data  # Node-RED
    return data
