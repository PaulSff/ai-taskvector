"""
RAG module: semantic search over workflows, nodes, and user documents.

Indexes:
- Workflows (Node-RED, n8n) - from local files or community repos
- Nodes/units - from Node-RED catalogue, n8n node types
- User documents - PDF, DOC, XLS via Docling

Usage:
  from rag import RAGIndex, search

  index = RAGIndex(persist_dir=".rag_index")
  index.build(workflows_dir="...", nodes_catalogue_url="...", docs_dir="...")
  results = index.search("temperature control workflow", top_k=5)
"""

from rag.indexer import RAGIndex
from rag.search import search

__all__ = ["RAGIndex", "search"]
