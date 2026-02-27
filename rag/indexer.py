"""
RAG index builder: workflows, nodes, and user documents.
Uses LlamaIndex + ChromaDB + sentence-transformers (CPU-friendly).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rag.extractors import (
    classify_json_for_rag,
    extract_n8n_workflow_meta,
    extract_node_red_catalogue_module,
    extract_node_red_library_entry,
    extract_node_red_workflow_meta,
    library_entry_meta_to_text,
    node_meta_to_text,
    workflow_meta_to_text,
)
from rag.extractors import load_workflow_json


def _chroma_safe_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """ChromaDB only allows str, int, float, None. Serialize list/dict to JSON string."""
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None or isinstance(v, (str, int, float)):
            out[k] = v
        elif isinstance(v, (list, dict)):
            out[k] = json.dumps(v) if v else ""
        else:
            out[k] = str(v)
    return out


def _get_llama_document(text: str, metadata: dict[str, Any]) -> Any:
    """Lazy import to avoid loading heavy deps when RAG not used."""
    from llama_index.core import Document

    return Document(text=text, metadata=_chroma_safe_metadata(metadata))


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

    def _docs_from_json_file(self, path: Path, data: dict | list, source: str | None = None) -> list[Any]:
        """
        Classify JSON (path + structure) and return LlamaIndex Documents.
        Uses path-based rules when mydata is structured (e.g. mydata/node-red/, mydata/n8n/).
        """
        kind = classify_json_for_rag(path, data)
        abs_path = str(path.absolute())
        src = source or path.name

        if kind == "n8n":
            if not isinstance(data, dict):
                return []
            meta = extract_n8n_workflow_meta(data, source=src)
            meta["file_path"] = abs_path
            meta["raw_json_path"] = abs_path
            return [_get_llama_document(workflow_meta_to_text(meta), meta)]

        if kind == "node_red":
            meta = extract_node_red_workflow_meta(data, source=src)
            meta["file_path"] = abs_path
            meta["raw_json_path"] = abs_path
            return [_get_llama_document(workflow_meta_to_text(meta), meta)]

        if kind == "node_red_catalogue":
            if not isinstance(data, dict):
                return []
            modules = data.get("modules")
            if not isinstance(modules, list):
                return []
            docs = []
            for mod in modules[:2000]:
                if not isinstance(mod, dict):
                    continue
                meta = extract_node_red_catalogue_module(mod, source=src)
                meta["file_path"] = abs_path
                meta["url"] = mod.get("url") or ""
                text = node_meta_to_text(meta)
                docs.append(_get_llama_document(text, meta))
            return docs

        if kind == "node_red_library":
            if not isinstance(data, list):
                return []
            docs = []
            for i, entry in enumerate(data[:500]):
                if not isinstance(entry, dict):
                    continue
                eid = entry.get("_id") or entry.get("id") or str(i)
                meta = extract_node_red_library_entry(entry, source=src, entry_id=str(eid))
                meta["file_path"] = abs_path
                meta["raw_json_path"] = abs_path
                text = library_entry_meta_to_text(meta)
                docs.append(_get_llama_document(text, meta))
            return docs

        if kind in ("n8n_nodes", "node_red_nodes"):
            # Node/n8n node folders: rules TBD; skip for now
            return []

        # generic or unknown: skip (do not index arbitrary JSON as workflow)
        return []

    def add_workflows_from_dir(self, dir_path: str | Path) -> list[Any]:
        """Scan directory for JSON; classify by path + structure and return LlamaIndex Documents."""
        docs: list[Any] = []
        root = Path(dir_path)
        if not root.is_dir():
            return docs

        for path in root.rglob("*.json"):
            data = load_workflow_json(path)
            if data is None:
                continue
            source = str(path.relative_to(root))
            docs.extend(self._docs_from_json_file(path, data, source=source))
        return docs

    def add_workflows_from_paths(self, paths: list[str | Path]) -> list[Any]:
        """Load JSON files from paths; classify by path + structure and return LlamaIndex Documents."""
        docs: list[Any] = []
        for p in paths:
            path = Path(p)
            if not path.is_file() or path.suffix.lower() != ".json":
                continue
            data = load_workflow_json(path)
            if data is None:
                continue
            docs.extend(self._docs_from_json_file(path, data))
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

    def add_documents_from_paths(self, paths: list[str | Path]) -> list[Any]:
        """Parse specific files with Docling; return LlamaIndex Documents."""
        from docling.document_converter import DocumentConverter

        docs: list[Any] = []
        converter = DocumentConverter()
        suffixes = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}

        for p in paths:
            path = Path(p)
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                result = converter.convert(str(path))
                text = result.document.export_to_markdown()
            except Exception:
                continue
            meta = {
                "content_type": "document",
                "source": path.name,
                "file_path": str(path.absolute()),
            }
            doc = _get_llama_document(text[:50000], meta)
            docs.append(doc)
        return docs

    def add_from_url_and_index(self, url: str) -> int:
        """
        Fetch from URL and add to index. Supports:
        - JSON workflow (Node-RED/n8n)
        - Node-RED catalogue JSON (modules)
        - Documents (PDF, DOC, etc.) - downloaded to temp file
        Returns number of items added.
        """
        import tempfile

        import requests

        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data = r.content
            ct = (r.headers.get("content-type") or "").lower()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch URL: {e}") from e

        if "json" in ct or url.rstrip("/").endswith(".json"):
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                raise ValueError("URL returned invalid JSON")
            if isinstance(parsed, dict) and "modules" in parsed:
                docs = self.add_nodes_from_catalogue_url(url)
            elif isinstance(parsed, dict) and "nodes" in parsed:
                meta = extract_n8n_workflow_meta(parsed, source=url)
                meta["file_path"] = url
                meta["raw_json_path"] = url
                docs = [_get_llama_document(workflow_meta_to_text(meta), meta)]
            elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                meta = extract_node_red_workflow_meta(parsed, source=url)
                meta["file_path"] = url
                meta["raw_json_path"] = url
                docs = [_get_llama_document(workflow_meta_to_text(meta), meta)]
            else:
                raise ValueError("JSON is not a workflow or catalogue")
        else:
            suffix = Path(url.split("?")[0]).suffix.lower() or ".bin"
            if suffix not in {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}:
                raise ValueError(f"Unsupported document type: {suffix}")
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(data)
                tmp_path = f.name
            try:
                return self.add_documents_and_index([tmp_path])
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        if not docs:
            return 0
        try:
            from llama_index.core.schema import TextNode

            self._load_index()
            nodes = [TextNode(text=d.text, metadata=d.metadata) for d in docs]
            self._index.insert_nodes(nodes)
            return len(docs)
        except Exception:
            self._build_index(docs)
            return len(docs)

    def add_documents_and_index(
        self,
        paths: list[str | Path],
        *,
        workflows_dir: str | Path | None = None,
        nodes_catalogue_url: str | None = None,
    ) -> int:
        """
        Add documents and/or workflow JSONs from file paths to the index.
        Supports PDF, DOC, XLS, etc. (via Docling) and .json (classified by path + structure).

        Recommended mydata layout for correct JSON classification:
          mydata/node-red/nodes/     → Node-RED nodes; catalogue.json here → catalogue (modules)
          mydata/node-red/workflows/ → Node-RED workflows; library = node-red-library-flows-refined.json
          mydata/n8n/workflows/      → n8n workflows
          mydata/n8n/nodes/          → n8n nodes (rules TBD; skipped for now)
        If index exists, inserts incrementally. Returns number of items added.
        """
        from llama_index.core.schema import TextNode

        doc_suffixes = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
        doc_paths = [p for p in paths if Path(p).suffix.lower() in doc_suffixes]
        wf_paths = [p for p in paths if Path(p).suffix.lower() == ".json"]

        docs = self.add_documents_from_paths(doc_paths)
        docs.extend(self.add_workflows_from_paths(wf_paths))
        if not docs:
            return 0
        try:
            self._load_index()
            nodes = [TextNode(text=d.text, metadata=d.metadata) for d in docs]
            self._index.insert_nodes(nodes)
            return len(docs)
        except Exception:
            pass
        all_docs = list(docs)
        if workflows_dir:
            all_docs = self.add_workflows_from_dir(workflows_dir) + all_docs
        if nodes_catalogue_url:
            all_docs = self.add_nodes_from_catalogue_url(nodes_catalogue_url) + all_docs
        self._build_index(all_docs)
        return len(docs)

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

    def _get_chroma_collection(self) -> Any:
        """Return the underlying ChromaDB collection for metadata queries."""
        import chromadb

        chroma_path = self.persist_dir / "chroma_db"
        chroma_path.mkdir(parents=True, exist_ok=True)
        db = chromadb.PersistentClient(path=str(chroma_path))
        return db.get_or_create_collection("rag", metadata={"hnsw:space": "cosine"})

    def delete_by_file_paths(self, file_paths: list[str]) -> int:
        """
        Remove from the index all nodes whose metadata file_path is in file_paths.
        Returns the number of file_paths that had at least one node removed (best effort).
        Used for incremental index updates (re-index only changed files).
        """
        if not file_paths:
            return 0
        try:
            coll = self._get_chroma_collection()
            ids_to_delete: list[str] = []
            # ChromaDB get(where=...) may not support $in; delete per path to be safe
            for fp in file_paths:
                try:
                    result = coll.get(
                        where={"file_path": {"$eq": fp}},
                        include=[],
                    )
                    if result and result.get("ids"):
                        ids_to_delete.extend(result["ids"])
                except Exception:
                    continue
            if ids_to_delete:
                coll.delete(ids=ids_to_delete)
            return len(file_paths)
        except Exception:
            return 0

    def get_node_by_id(self, node_id: str) -> dict[str, Any] | None:
        """
        Look up a node (catalogue module) by id from the RAG index.
        Returns metadata dict or None if not found.
        Used by import_unit edit to resolve node_id to node_types.
        """
        try:
            coll = self._get_chroma_collection()
            result = coll.get(
                where={"$and": [{"content_type": {"$eq": "node"}}, {"id": {"$eq": str(node_id)}}]},
                include=["metadatas"],
            )
            if result and result.get("metadatas") and len(result["metadatas"]) > 0:
                return dict(result["metadatas"][0])
        except Exception:
            pass
        return None

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
