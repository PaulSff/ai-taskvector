"""
RAG context for prompts: query → formatted "Relevant context from knowledge base" block.

Uses the RAG index (vector search). No GUI dependency: accepts explicit persist_dir and
embedding_model so it can be used from the GUI when building the prompt outside the workflow.
"""
from __future__ import annotations

# Limits (same as GUI for consistency)
RAG_CONTEXT_MAX_CHARS = 2000
RAG_TOP_K = 8
WORKFLOW_DESIGNER_RAG_MAX_CHARS = 1200
WORKFLOW_DESIGNER_RAG_TOP_K = 5
RAG_MIN_SCORE = 0.48


def get_rag_context_for_prompt(
    query: str,
    persist_dir: str,
    embedding_model: str,
    *,
    assistant: str = "Workflow Designer",
    top_k: int | None = None,
) -> str:
    """
    Retrieve relevant context from the RAG index and format for the prompt.

    Uses index.search(query, top_k, content_type). Only results with score >= RAG_MIN_SCORE
    are included. Returns formatted block or "" if query empty, index unavailable, or no results.

    Args:
        query: User message (search query)
        persist_dir: RAG index directory (e.g. from settings or unit params)
        embedding_model: Embedding model name for RAGIndex
        assistant: "Workflow Designer" or "RL Coach" (drives max_chars, default top_k, snippet length)
        top_k: Optional max results; clamped 1–50. Default from assistant.

    Returns:
        "Relevant context from knowledge base: ..." block, or ""
    """
    query = (query or "").strip()
    if not query:
        return ""
    persist_dir = (persist_dir or "").strip()
    if not persist_dir:
        return ""
    try:
        from rag.indexer import RAGIndex

        index = RAGIndex(persist_dir=persist_dir, embedding_model=embedding_model or None)
    except Exception:
        return ""

    content_type = None
    max_chars = WORKFLOW_DESIGNER_RAG_MAX_CHARS if assistant == "Workflow Designer" else RAG_CONTEXT_MAX_CHARS
    default_top_k = WORKFLOW_DESIGNER_RAG_TOP_K if assistant == "Workflow Designer" else RAG_TOP_K
    if top_k is not None:
        top_k = max(1, min(50, int(top_k)))
    else:
        top_k = default_top_k
    snippet_max = 400 if assistant == "Workflow Designer" else 300
    try:
        results = index.search(query, top_k=top_k, content_type=content_type)
    except Exception:
        return ""

    if not results:
        return ""

    typed: list[tuple[str, str]] = []
    total = 0
    for r in results:
        if RAG_MIN_SCORE is not None:
            score = r.get("score")
            if score is not None and score < RAG_MIN_SCORE:
                continue
        meta = r.get("metadata") or {}
        text = (r.get("text") or "").strip()
        if not text:
            continue
        ct = meta.get("content_type", "") or "other"
        source = meta.get("file_path") or meta.get("raw_json_path") or meta.get("source") or meta.get("id") or "?"
        label = meta.get("name") or source
        snippet = text.replace("\n", " ")[:snippet_max]
        if ct and ct != "other":
            entry = f"[{ct}] {label}: {snippet}"
        else:
            entry = f"{label}: {snippet}"
        if total + len(entry) + 2 > max_chars:
            break
        typed.append((ct, entry))
        total += len(entry) + 2

    if not typed:
        return ""

    section_sep = "\n\n--- "
    section_end = " ---\n\n"
    order = ("document", "workflow", "flow_library", "node", "other")
    by_type: dict[str, list[str]] = {}
    for ct, entry in typed:
        key = ct if ct in order else "other"
        by_type.setdefault(key, []).append(entry)
    block_parts = ["Relevant context from knowledge base:"]
    section_labels = {"document": "Documents", "workflow": "Workflows", "flow_library": "Flow libraries", "node": "Nodes", "other": "Other"}
    for key in order:
        if key not in by_type:
            continue
        label = section_labels.get(key, key.replace("_", " ").capitalize() + "s")
        block_parts.append(section_sep + label + section_end + "\n\n".join(by_type[key]))
    block = "".join(block_parts)
    block += "\n\nUse file_path or raw_json_path from above for import_workflow when applicable."
    return block
