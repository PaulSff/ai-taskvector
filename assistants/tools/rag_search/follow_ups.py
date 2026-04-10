"""rag_search tool: follow-up prompt fragments."""

from assistants.tools.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

RAG_SEARCH_FOLLOW_UP_PREFIX = "IMPORTANT: You requested the RAG search. You must check the search results.\n\n"
RAG_SEARCH_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
