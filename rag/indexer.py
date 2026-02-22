"""
RAG index builder: workflows, nodes, and user documents.
Uses LlamaIndex + ChromaDB + sentence-transformers (CPU-friendly).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rag.extractors import (
    extract_n8n_workflow_meta,
    extract_node_red_catalogue_module,
    extract_node_red_workflow_meta,
    node_meta_to_text,
    workflow_meta_to_text,
)
from rag.extractors import load_workflow_json


def _get_llama_document(text: str, metadata: dict[str, Any]) -> Any:
    """Lazy import to avoid loading heavy deps when RAG not used."""
    from llama_index.core import Document

    return Document(text=text, metadata=metadata)


def _get_embed_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> Any:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    return HuggingFaceEmbedding(model_name=model_name or "sentence-transformers/all-MiniLM-L6-v2")


def _get_chroma_vector_store(persist_dir: str) -> tuple[Any, Any]:
    from pathlib import Path as P

    from llama_index.core import StorageContext
    from llama_index.vector_stores.chroma import ChromaVectorStore
    import chromadb

    persist_path = P(persist_dir)
    persist_path.mkdir(parents=True, exist_ok=True)
    chroma_path = persist_path / "chroma_db"

    db = chromadb.PersistentClient(path=str(chroma_path))
    chroma_collection = db.get_or_create_collection("rag", metadata={"hnsw:space": "cosine"})
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return vector_store, storage_context


class RAGIndex:
    """
    Build and manage a RAG index over workflows, nodes, and documents.
    """

    def __init__(
        self,
        persist_dir: str = ".rag_index",
        embedding_model: str | None = None,
    ):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model = (embedding_model or "sentence-transformers/all-MiniLM-L6-v2").strip()
        self._index = None
        self._vector_store = None
        self._storage_context = None

    def _build_index(self, documents: list[Any]) -> Any:
        from llama_index.core import VectorStoreIndex

        embed_model = _get_embed_model(self.embedding_model)
        self._vector_store, self._storage_context = _get_chroma_vector_store(str(self.persist_dir))
        self._index = VectorStoreIndex.from_documents(
            documents,
            storage_context=self._storage_context,
            embed_model=embed_model,
            show_progress=True,
        )
        return self._index

    def _load_index(self) -> Any:
        from llama_index.core import VectorStoreIndex

        self._vector_store, self._storage_context = _get_chroma_vector_store(str(self.persist_dir))
        self._index = VectorStoreIndex.from_vector_store(
            self._vector_store,
            storage_context=self._storage_context,
            embed_model=_get_embed_model(self.embedding_model),
        )
        return self._index

    def add_workflows_from_dir(self, dir_path: str | Path) -> list[Any]:
        """Scan directory for Node-RED and n8n JSON workflows; return LlamaIndex Documents."""
        docs: list[Any] = []
        root = Path(dir_path)
        if not root.is_dir():
            return docs

        for path in root.rglob("*.json"):
            data = load_workflow_json(path)
            if data is None:
                continue
            rel = path.relative_to(root)
            source = str(rel)

            if isinstance(data, dict) and data.get("nodes") and data.get("connections"):
                meta = extract_n8n_workflow_meta(data, source=source)
            else:
                meta = extract_node_red_workflow_meta(data, source=source)

            meta["file_path"] = str(path.absolute())
            meta["raw_json_path"] = str(path.absolute())
            text = workflow_meta_to_text(meta)
            docs.append(_get_llama_document(text, meta))
        return docs

    def add_nodes_from_catalogue_url(self, url: str) -> list[Any]:
        """Fetch Node-RED catalogue JSON and create documents for each module."""
        import requests

        docs: list[Any] = []
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return docs

        modules = data.get("modules") if isinstance(data, dict) else []
        if not isinstance(modules, list):
            return docs

        for mod in modules[:2000]:  # cap to avoid huge index
            if not isinstance(mod, dict):
                continue
            meta = extract_node_red_catalogue_module(mod, source="node_red_catalogue")
            meta["url"] = mod.get("url") or ""
            text = node_meta_to_text(meta)
            docs.append(_get_llama_document(text, meta))
        return docs

    def add_nodes_from_catalogue_file(self, path: str | Path) -> list[Any]:
        """Load Node-RED catalogue from local JSON file."""
        docs: list[Any] = []
        p = Path(path)
        if not p.exists():
            return docs
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return docs
        modules = data.get("modules") if isinstance(data, dict) else []
        if not isinstance(modules, list):
            return docs
        for mod in modules[:2000]:
            if not isinstance(mod, dict):
                continue
            meta = extract_node_red_catalogue_module(mod, source=str(p))
            meta["url"] = mod.get("url") or ""
            text = node_meta_to_text(meta)
            docs.append(_get_llama_document(text, meta))
        return docs

    def add_documents_from_dir(self, dir_path: str | Path) -> list[Any]:
        """Parse PDF, DOC, XLS in directory with Docling; return LlamaIndex Documents."""
        from docling.document_converter import DocumentConverter

        docs: list[Any] = []
        root = Path(dir_path)
        if not root.is_dir():
            return docs

        converter = DocumentConverter()
        suffixes = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}

        for path in root.rglob("*"):
            if path.suffix.lower() not in suffixes:
                continue
            try:
                result = converter.convert(str(path))
                text = result.document.export_to_markdown()
            except Exception:
                continue

            meta = {
                "content_type": "document",
                "source": str(path.relative_to(root)),
                "file_path": str(path.absolute()),
            }
            doc = _get_llama_document(text[:50000], meta)  # cap length
            docs.append(doc)
        return docs

    def build(
        self,
        *,
        workflows_dir: str | Path | None = None,
        nodes_catalogue_url: str | None = None,
        nodes_catalogue_file: str | Path | None = None,
        docs_dir: str | Path | None = None,
    ) -> None:
        """Build the full index from workflows, nodes, and documents."""
        all_docs: list[Any] = []

        if workflows_dir:
            wf_docs = self.add_workflows_from_dir(workflows_dir)
            all_docs.extend(wf_docs)

        if nodes_catalogue_url:
            node_docs = self.add_nodes_from_catalogue_url(nodes_catalogue_url)
            all_docs.extend(node_docs)
        elif nodes_catalogue_file:
            node_docs = self.add_nodes_from_catalogue_file(nodes_catalogue_file)
            all_docs.extend(node_docs)

        if docs_dir:
            doc_docs = self.add_documents_from_dir(docs_dir)
            all_docs.extend(doc_docs)

        if not all_docs:
            raise ValueError("No documents to index. Provide at least one of workflows_dir, nodes_catalogue_url/file, or docs_dir.")

        self._build_index(all_docs)

    def get_retriever(self, similarity_top_k: int = 10):
        """Return a retriever for search. Loads index from disk if not already built this session."""
        if self._index is None:
            self._load_index()
        return self._index.as_retriever(similarity_top_k=similarity_top_k)

    def search(self, query: str, top_k: int = 10, content_type: str | None = None) -> list[dict]:
        """
        Search the index. Returns list of {text, metadata, score}.
        content_type: optional filter - "workflow", "node", or "document"
        """
        retriever = self.get_retriever(similarity_top_k=top_k * 2)  # fetch extra for filtering
        nodes = retriever.retrieve(query)
        results = []
        for n in nodes:
            meta = n.metadata or {}
            if content_type and meta.get("content_type") != content_type:
                continue
            results.append({
                "text": n.get_content(),
                "metadata": meta,
                "score": getattr(n, "score", None),
            })
            if len(results) >= top_k:
                break
        return results
