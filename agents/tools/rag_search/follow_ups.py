"""rag_search tool: follow-up prompt fragments."""

RAG_SEARCH_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the RAG search. You must check the search results.\n\n"
)
RAG_SEARCH_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the search results for the user. Use read_file action to explore the source, if needed. "
    "Respond in {session_language}."
)
