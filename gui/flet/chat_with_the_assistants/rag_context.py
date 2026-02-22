"""
RAG-augmented context for assistants: retrieve relevant workflows, nodes, and documents
and inject them into the prompt for Workflow Designer and RL Coach.
"""
from __future__ import annotations

RAG_CONTEXT_MAX_CHARS = 2000
RAG_TOP_K = 8


def get_rag_context(query: str, assistant: str) -> str:
    """
    Retrieve relevant context from the RAG index for the given assistant.
    Returns formatted string to inject into the prompt, or empty string if unavailable.

    Args:
        query: User message (used as search query)
        assistant: "Workflow Designer" or "RL Coach"

    Returns:
        Formatted "Relevant context from knowledge base: ..." block, or ""
    """
    query = (query or "").strip()
    if not query:
        return ""
    try:
        from gui.flet.components.settings import get_rag_embedding_model, get_rag_index_dir
        from rag.indexer import RAGIndex

        index = RAGIndex(
            persist_dir=str(get_rag_index_dir()),
            embedding_model=get_rag_embedding_model(),
        )
    except (ImportError, Exception):
        return ""

    content_type = None
    if assistant == "Workflow Designer":
        # Prefer workflows and nodes; one search without filter gets both
        content_type = None
    # RL Coach: no filter (documents + workflows + nodes all useful)

    try:
        results = index.search(query, top_k=RAG_TOP_K, content_type=content_type)
    except Exception:
        return ""

    if not results:
        return ""

    parts: list[str] = []
    total = 0
    for r in results:
        meta = r.get("metadata") or {}
        text = (r.get("text") or "").strip()
        if not text:
            continue
        ct = meta.get("content_type", "")
        source = meta.get("file_path") or meta.get("raw_json_path") or meta.get("source") or meta.get("id") or "?"
        label = meta.get("name") or source
        # One line per result; truncate long text
        snippet = text.replace("\n", " ")[:300]
        if ct:
            entry = f"[{ct}] {label}: {snippet}"
        else:
            entry = f"{label}: {snippet}"
        if total + len(entry) + 2 > RAG_CONTEXT_MAX_CHARS:
            break
        parts.append(entry)
        total += len(entry) + 2

    if not parts:
        return ""

    block = "Relevant context from knowledge base:\n" + "\n".join(parts)
    block += f"\n\nUse file_path, raw_json_path, or id from above for import_workflow / import_unit when applicable."
    return block
