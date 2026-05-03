"""
RAG module: semantic search over workflows, nodes, and user documents.

Indexes:
- Workflows (Node-RED, n8n, TaskVector canonical) - from local files
- Node catalogues - local JSON file via upload pipeline (JsonFlattenExtract)
- User documents - PDF, DOC, XLS via Docling

Usage:
  from rag import RAGIndex, search

  index = RAGIndex(persist_dir=".rag_index")
  index.build(workflows_dir="...", nodes_catalogue_file="/path/to/catalogue.json", docs_dir="...")
  results = index.search("temperature control workflow", top_k=5)
"""

from rag.indexer import RAGIndex
from units.rag.rag_search import search

__all__ = ["RAGIndex", "search"]
