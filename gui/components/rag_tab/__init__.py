"""RAG tab package: knowledge-base UI, mydata copy helpers, chat upload flow."""

from .helpers import (
    RAG_ADD_FOLDER_SUFFIXES,
    RAG_DOC_SUFFIXES,
    RAG_WORKFLOW_SUFFIXES,
    build_rag_update_overrides_public,
    copy_rag_source_paths_to_mydata,
    run_rag_file_pick_copy_and_index,
)
from .tab import build_rag_tab

__all__ = [
    "RAG_ADD_FOLDER_SUFFIXES",
    "RAG_DOC_SUFFIXES",
    "RAG_WORKFLOW_SUFFIXES",
    "build_rag_tab",
    "build_rag_update_overrides_public",
    "copy_rag_source_paths_to_mydata",
    "run_rag_file_pick_copy_and_index",
]
