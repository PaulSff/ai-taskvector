from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

CHAT_HISTORY_EXTRACT_INPUT_PORTS = [("data", "Any"), ("file_path", "Any")]
CHAT_HISTORY_EXTRACT_OUTPUT_PORTS = [("items", "Any"), ("error", "str")]


# defaults (can be overridden via params)
DEFAULT_MAX_MESSAGES = 8000
DEFAULT_CHUNK_CHARS = 4000
DEFAULT_GROUP_SIZE = 4
DEFAULT_GROUP_OVERLAP = 0
DEFAULT_INCLUDE_TEXT = True
DEFAULT_INCLUDE_FEEDBACKS = True
DEFAULT_ROLE_FALLBACK = "?"  # set to "" to mimic extractors.py omission behavior
DEFAULT_CHUNK_MODE = "none"  # "none" (grouping) or "char" (character chunking)


# -----------------------------
# Helpers
# -----------------------------


def _to_string(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, dict)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except Exception:
            return str(val)
    return str(val)


def _messages(raw: dict | list) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and "messages" in raw:
        msgs = raw.get("messages") or []
    elif isinstance(raw, list):
        msgs = raw
    else:
        return []
    return [m for m in msgs if isinstance(m, dict)]


def _extract_meta(
    raw: dict | list,
    source: str,
    *,
    include_text: bool = True,
    include_feedbacks: bool = True,
) -> dict[str, Any]:
    msgs = _messages(raw)

    roles = set()
    agents = set()
    timestamps: list[str] = []
    feedbacks: list[str] = []
    content_texts: list[str] = []

    for m in msgs:
        if m.get("role"):
            roles.add(str(m["role"]))
        if m.get("agent"):
            agents.add(str(m["agent"]))
        if m.get("ts"):
            timestamps.append(str(m["ts"]))

        if include_feedbacks and m.get("feedback"):
            fb = m["feedback"]
            if isinstance(fb, dict):
                fb_text = " | ".join(f"{k}:{v}" for k, v in fb.items())
            else:
                fb_text = str(fb)
            feedbacks.append(fb_text)

        content = m.get("content")
        if content is None:
            pass
        elif isinstance(content, list):
            content_texts.append(" ".join(_to_string(x) for x in content))
        else:
            content_texts.append(_to_string(content))

    name = f"Chat history ({len(msgs)} messages)"

    meta: dict[str, Any] = {
        "content_type": "chat_history",
        "format": "chat_history",
        "name": name,
        "source": source,
        "messages_count": len(msgs),
        "roles": list(roles),
        "agents": list(agents),
        "timestamps": timestamps,
    }

    if include_text and content_texts:
        meta["text"] = " | ".join(content_texts[:1000])
    if include_feedbacks and feedbacks:
        meta["feedbacks"] = feedbacks

    return meta


def _format_message(
    m: dict[str, Any], role_fallback: str = DEFAULT_ROLE_FALLBACK
) -> str:
    role = m.get("role")
    role_str = str(role).strip() if role is not None else role_fallback or ""

    msg_content = m.get("content")
    if msg_content is None:
        body = ""
    elif isinstance(msg_content, list):
        body = " ".join(_to_string(x) for x in msg_content)
    else:
        body = _to_string(msg_content)
    body = body.strip()

    extras: list[str] = []
    if m.get("feedback"):
        extras.append(f"feedback={_to_string(m['feedback'])}")
    if m.get("agent"):
        extras.append(f"agent={_to_string(m['agent'])}")
    if m.get("ts"):
        extras.append(f"ts={_to_string(m['ts'])}")

    suffix = (" | " + " ".join(extras)) if extras else ""

    if role_str:
        return (
            f"{role_str}: {body}{suffix}".rstrip()
            if (body or suffix)
            else f"{role_str}:"
        )
    else:
        # If no role and nothing else, return empty string (extractors.py omits such lines)
        if body or suffix:
            return f"{body}{suffix}".rstrip()
        return ""


def _group_messages(
    messages: list[dict[str, Any]],
    group_size: int,
    overlap: int,
) -> list[list[dict[str, Any]]]:
    if group_size <= 0:
        group_size = 1
    if overlap >= group_size:
        overlap = group_size - 1
    step = group_size - overlap
    groups: list[list[dict[str, Any]]] = []
    for i in range(0, len(messages), step):
        window = messages[i : i + group_size]
        if window:
            groups.append(window)
    return groups


def _build_text(group: list[dict[str, Any]], role_fallback: str) -> str:
    return "\n".join(
        line
        for line in (
            _format_message(m, role_fallback) for m in group if isinstance(m, dict)
        )
        if line
    )


def _lines_from_messages(
    messages: list[dict[str, Any]], role_fallback: str
) -> list[str]:
    lines: list[str] = []
    for m in messages:
        line = _format_message(m, role_fallback)
        if line:
            lines.append(line)
    return lines


def _slim_chat_meta_for_index(meta: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "content_type",
        "format",
        "name",
        "source",
        "messages_count",
        "roles",
        "agents",
    )
    slim: dict[str, Any] = {k: meta[k] for k in keys if k in meta}
    fb = meta.get("feedbacks")
    if fb:
        slim["feedbacks"] = fb[:40] if isinstance(fb, list) and len(fb) > 40 else fb
    ts = meta.get("timestamps")
    if ts:
        slim["timestamps"] = ts[:80] if isinstance(ts, list) and len(ts) > 80 else ts
    return slim


# -----------------------------
# Step
# -----------------------------


def _chat_history_extract_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
):
    try:
        raw = inputs.get("data")

        if not isinstance(raw, (dict, list)):
            return {"items": [], "error": "data must be dict or list"}, state

        # RagDetectOrigin / PayloadTransform envelope: {file_path, parsed, origin}
        envelope_fp = ""
        if isinstance(raw, dict) and "parsed" in raw:
            envelope_fp = str(raw.get("file_path") or "").strip()
            parsed = raw.get("parsed")
            if isinstance(parsed, (dict, list)):
                raw = parsed

        # -----------------------------
        # file / source resolution
        # -----------------------------
        fp = ""
        if isinstance(raw, dict):
            fp = str(raw.get("file_path") or "").strip()

        fp_w = inputs.get("file_path")
        if isinstance(fp_w, str) and fp_w.strip():
            fp = fp_w.strip()
        elif envelope_fp:
            fp = envelope_fp

        path = Path(fp) if fp else Path(".")

        if not raw and fp and path.suffix.lower() == ".json" and path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                return {"items": [], "error": str(e)}, state

        source = ""
        if isinstance(raw, dict):
            source = str(raw.get("source") or "").strip()
        source = source or (Path(fp).name if fp else "")

        messages = _messages(raw)

        if not messages:
            return {"items": [], "error": ""}, state

        # -----------------------------
        # params
        # -----------------------------
        group_size = int(params.get("group_size", DEFAULT_GROUP_SIZE))
        overlap = int(params.get("group_overlap", DEFAULT_GROUP_OVERLAP))
        group_size = max(1, min(group_size, 50))
        overlap = max(0, min(overlap, group_size - 1))

        max_messages = int(params.get("max_messages", DEFAULT_MAX_MESSAGES))
        include_text = bool(params.get("include_text", DEFAULT_INCLUDE_TEXT))
        include_feedbacks = bool(
            params.get("include_feedbacks", DEFAULT_INCLUDE_FEEDBACKS)
        )
        role_fallback = params.get("role_fallback", DEFAULT_ROLE_FALLBACK)
        chunk_mode = params.get("chunk_mode", DEFAULT_CHUNK_MODE)
        chunk_chars = int(params.get("chunk_chars", DEFAULT_CHUNK_CHARS))

        messages = messages[:max_messages]

        meta = _extract_meta(
            raw, source, include_text=include_text, include_feedbacks=include_feedbacks
        )
        meta["file_path"] = str(path)
        meta["raw_json_path"] = str(path)
        meta["origin"] = "chat_history"

        items: list[dict[str, Any]] = []

        if chunk_mode == "char":
            # character chunking path (align with extractors.build_chat_history_index_documents)
            lines = _lines_from_messages(messages, role_fallback)
            if not lines:
                return {"items": [], "error": ""}, state

            slim = _slim_chat_meta_for_index(meta)
            slim["file_path"] = str(path)
            slim["raw_json_path"] = str(path)
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
            for i, chunk in enumerate(chunks):
                item_meta = {**slim, "chunk_index": i, "chunk_count": n}
                header = (
                    f"{meta.get('name', 'Chat history')} — excerpt {i + 1} of {n} "
                    f"(source: {source})\n\n"
                )
                items.append(
                    {
                        "text": header + chunk,
                        "metadata": item_meta,
                    }
                )

        else:
            # grouping path (semantic grouping by turns)
            groups = _group_messages(messages, group_size, overlap)
            for i, group in enumerate(groups):
                text = _build_text(group, role_fallback)
                items.append(
                    {
                        "text": text,
                        "metadata": {
                            **meta,
                            "group_index": i,
                            "group_size": len(group),
                            "total_groups": len(groups),
                        },
                    }
                )

        return {"items": items, "error": ""}, state

    except Exception as e:
        return {"items": [], "error": str(e)}, state


# -----------------------------
# Registration
# -----------------------------


def register_chat_history_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="ChatHistoryExtract",
            input_ports=CHAT_HISTORY_EXTRACT_INPUT_PORTS,
            output_ports=CHAT_HISTORY_EXTRACT_OUTPUT_PORTS,
            step_fn=_chat_history_extract_step,
            environment_tags_are_agnostic=True,
            description="Chat history extractor with structure-aware grouping (pre-chunk stage); optional char-based chunking to match index document output.",
        )
    )
