"""rag_search skill: follow-up prompt fragments."""

from assistants.skills.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

RAG_SEARCH_FOLLOW_UP_PREFIX = "IMPORTANT: You requested the RAG search. You must check the search results.\n\n"
RAG_SEARCH_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
