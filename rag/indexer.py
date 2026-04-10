"""
RAG index builder: workflows, nodes, and user documents.
Uses LlamaIndex + ChromaDB + sentence-transformers (CPU-friendly).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from rag.discriminant import classify_json_for_rag
from rag.extractors import (
    build_chat_history_index_documents,
    extract_canonical_workflow_meta,
    extract_n8n_workflow_meta,
    extract_node_red_catalogue_module,
    extract_node_red_workflow_meta,
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


# Plain-text formats: read as UTF-8 (no Docling). Must match rag.context_updater.RAG_PLAIN_TEXT_SUFFIXES.
_PLAIN_TEXT_SUFFIXES = {".csv", ".txt", ".yaml", ".yml", ".xml", ".log", ".ini", ".cfg", ".conf", ".env", ".tsv", ".rst"}
_MAX_PLAIN_TEXT_CHARS = 50000


def _relative_under_any_root(path: Path, roots: Sequence[str | Path]) -> str | None:
    """Return POSIX path relative to the first root that contains path, else None."""
    pr = path.resolve()
    for r in roots:
        try:
            rr = Path(r).resolve()
            return str(pr.relative_to(rr)).replace("\\", "/")
        except ValueError:
            continue
    return None


# Doc-to-text workflow: Inject → LoadDocument → TablesToText → Aggregate → Prompt (pandas + openpyxl for tables).
_DOC_TO_TEXT_WORKFLOW_REL = "gui/flet/components/workflow/assistants/doc_to_text.json"


def _get_doc_to_text_workflow_path() -> Path:
    """Path to doc_to_text workflow; from settings when available, else repo-relative."""
    try:
        from gui.flet.components.settings import get_doc_to_text_workflow_path
        return get_doc_to_text_workflow_path()
    except ImportError:
        pass
    root = Path(__file__).resolve().parent.parent
    return root / _DOC_TO_TEXT_WORKFLOW_REL


def _document_to_text_via_workflow(path: Path) -> str | None:
    """Run doc_to_text workflow for path; return system_prompt (document text) or None on failure."""
    wf_path = _get_doc_to_text_workflow_path()
    if not wf_path.is_file():
        return None
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
        from runtime.run import run_workflow
        outputs = run_workflow(
            wf_path,
            initial_inputs={"inject_path": {"data": str(path.resolve())}},
        )
    except Exception:
        return None
    if not isinstance(outputs, dict):
        return None
    prompt_out = outputs.get("prompt") or {}
    text = prompt_out.get("system_prompt") if isinstance(prompt_out, dict) else None
    return (text or "").strip() or None


def _get_llama_document(text: str, metadata: dict[str, Any]) -> Any:
    """Lazy import to avoid loading heavy deps when RAG not used."""
    from llama_index.core import Document

    return Document(text=text, metadata=_chroma_safe_metadata(metadata))


def _default_rag_embedding_model() -> str:
    """Default embedding model: from settings when available."""
    try:
        from gui.flet.components.settings import get_rag_embedding_model
        return get_rag_embedding_model()
    except ImportError:
        return "sentence-transformers/all-MiniLM-L6-v2"


def _get_embed_model(model_name: str | None = None) -> Any:
    import os

    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    try:
        from gui.flet.components.settings import get_rag_offline

        if get_rag_offline():
            os.environ["HF_HUB_OFFLINE"] = "1"
    except ImportError:
        pass
    return HuggingFaceEmbedding(model_name=model_name or _default_rag_embedding_model())


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
        self.embedding_model = (embedding_model or _default_rag_embedding_model()).strip()
        self._index = None
        self._vector_store = None
        self._storage_context = None

    def _build_index(self, documents: list[Any]) -> Any:
        from llama_index.core import VectorStoreIndex

        if documents:
            print(f"RAG: Building vector index ({len(documents)} chunk(s))...", flush=True)
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

        # Map classification kind to origin string for import_workflow (node-red, n8n, canonical).
        _ORIGIN_FOR_KIND = {"n8n": "n8n", "node_red": "node-red", "canonical": "canonical"}

        if kind == "n8n":
            if not isinstance(data, dict):
                return []
            meta = extract_n8n_workflow_meta(data, source=src)
            meta["file_path"] = abs_path
            meta["raw_json_path"] = abs_path
            meta["origin"] = _ORIGIN_FOR_KIND.get(kind, kind)
            return [_get_llama_document(workflow_meta_to_text(meta), meta)]

        if kind == "canonical":
            if not isinstance(data, dict):
                return []
            meta = extract_canonical_workflow_meta(data, source=src)
            meta["file_path"] = abs_path
            meta["raw_json_path"] = abs_path
            meta["origin"] = _ORIGIN_FOR_KIND.get(kind, kind)
            return [_get_llama_document(workflow_meta_to_text(meta), meta)]

        if kind == "node_red":
            meta = extract_node_red_workflow_meta(data, source=src)
            meta["file_path"] = abs_path
            meta["raw_json_path"] = abs_path
            meta["origin"] = _ORIGIN_FOR_KIND.get(kind, kind)
            return [_get_llama_document(workflow_meta_to_text(meta), meta)]

        if kind == "chat_history":
            # Chunked documents: full transcript is indexed (not a single 2k-truncated blob).
            pairs = build_chat_history_index_documents(
                data, source=src, file_path=abs_path
            )
            if not pairs:
                return []
            return [_get_llama_document(text, md) for text, md in pairs]

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
        try:
            from tqdm import tqdm
            path_iter = tqdm(paths, desc="RAG workflows", unit="file", leave=False, disable=not sys.stdout.isatty())
        except ImportError:
            path_iter = paths
        for p in path_iter:
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

    def add_chat_history_from_json(self, path: str | Path, source: str | None = None) -> list[Any]:
        """
        Load a chat history JSON file (dict with 'messages' or list of messages),
        extract metadata, convert to Llama document, and return list with a single document.
        """
        p = Path(path)
        if not p.is_file() or p.suffix.lower() != ".json":
            return []

        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []

        src = source or p.name
        abs_p = str(p.absolute())
        pairs = build_chat_history_index_documents(raw, source=src, file_path=abs_p)
        if not pairs:
            return []
        return [_get_llama_document(text, md) for text, md in pairs]

    def add_documents_from_dir(self, dir_path: str | Path) -> list[Any]:
        """Parse PDF, DOC, XLS in directory via doc_to_text workflow (Docling + pandas tables). Skips files when workflow returns no text."""
        docs: list[Any] = []
        root = Path(dir_path)
        if not root.is_dir():
            return docs

        suffixes = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
        for path in root.rglob("*"):
            if path.suffix.lower() not in suffixes:
                continue
            if "encrypted" in path.name.lower():
                continue
            text = _document_to_text_via_workflow(path)
            if not text:
                continue
            meta = {
                "content_type": "document",
                "source": str(path.relative_to(root)),
                "file_path": str(path.absolute()),
            }
            doc = _get_llama_document(text[:50000], meta)
            docs.append(doc)
        return docs

    def add_documents_from_paths(self, paths: list[str | Path]) -> list[Any]:
        """Parse specific files via doc_to_text workflow (Docling + pandas tables). Skips files when workflow returns no text."""
        docs: list[Any] = []
        suffixes = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
        try:
            from tqdm import tqdm
            path_iter = tqdm(paths, desc="RAG documents", unit="file", leave=False, disable=not sys.stdout.isatty())
        except ImportError:
            path_iter = paths
        for p in path_iter:
            path = Path(p)
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if "encrypted" in path.name.lower():
                continue
            text = _document_to_text_via_workflow(path)
            if not text:
                continue
            meta = {
                "content_type": "document",
                "source": path.name,
                "file_path": str(path.absolute()),
            }
            doc = _get_llama_document(text[:50000], meta)
            docs.append(doc)
        return docs

    def add_plain_text_from_paths(self, paths: list[str | Path]) -> list[Any]:
        """Index plain-text files (CSV, TXT, YAML, etc.) by reading as UTF-8. No Docling."""
        docs: list[Any] = []
        try:
            from tqdm import tqdm
            path_iter = tqdm(paths, desc="RAG plain text", unit="file", leave=False, disable=not sys.stdout.isatty())
        except ImportError:
            path_iter = paths
        for p in path_iter:
            path = Path(p)
            if not path.is_file() or path.suffix.lower() not in _PLAIN_TEXT_SUFFIXES:
                continue
            if "encrypted" in path.name.lower():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            text = text.strip()
            if not text:
                continue
            text = text[:_MAX_PLAIN_TEXT_CHARS]
            meta = {
                "content_type": "document",
                "source": path.name,
                "file_path": str(path.absolute()),
            }
            docs.append(_get_llama_document(text, meta))
        return docs

    def _docs_from_unit_py_paths(
        self,
        paths: list[str | Path],
        unit_source_roots: Sequence[str | Path],
    ) -> list[Any]:
        """Index .py under unit_source_roots as UTF-8 plain text with content_type unit_source."""
        docs: list[Any] = []
        if not unit_source_roots:
            return docs
        try:
            from tqdm import tqdm

            path_iter = tqdm(
                paths,
                desc="RAG unit source",
                unit="file",
                leave=False,
                disable=not sys.stdout.isatty(),
            )
        except ImportError:
            path_iter = paths
        for p in path_iter:
            path = Path(p)
            if not path.is_file() or path.suffix.lower() != ".py":
                continue
            if "encrypted" in path.name.lower():
                continue
            rel = _relative_under_any_root(path, unit_source_roots)
            if rel is None:
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            body = body.strip()
            if not body:
                continue
            prefix = f"Unit source ({rel}):\n\n"
            text = (prefix + body)[:_MAX_PLAIN_TEXT_CHARS]
            meta = {
                "content_type": "unit_source",
                "source": rel,
                "file_path": str(path.resolve()),
            }
            docs.append(_get_llama_document(text, meta))
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
            kind = classify_json_for_rag(Path(url.split("?")[0] or "remote.json"), parsed)
            if kind == "chat_history":
                pairs = build_chat_history_index_documents(
                    parsed, source=url, file_path=url
                )
                docs = [_get_llama_document(t, m) for t, m in pairs] if pairs else []
            elif isinstance(parsed, dict) and "modules" in parsed:
                docs = self.add_nodes_from_catalogue_url(url)
            elif isinstance(parsed, dict) and "nodes" in parsed:
                meta = extract_n8n_workflow_meta(parsed, source=url)
                meta["file_path"] = url
                meta["raw_json_path"] = url
                meta["origin"] = "n8n"
                docs = [_get_llama_document(workflow_meta_to_text(meta), meta)]
            elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                meta = extract_node_red_workflow_meta(parsed, source=url)
                meta["file_path"] = url
                meta["raw_json_path"] = url
                meta["origin"] = "node-red"
                docs = [_get_llama_document(workflow_meta_to_text(meta), meta)]
            else:
                raise ValueError("JSON is not a workflow, catalogue, or chat history")
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
        unit_source_roots: Sequence[str | Path] | None = None,
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

        unit_source_roots: optional roots (e.g. units_dir). ``.py`` files under a root are indexed
        as UTF-8 with metadata content_type ``unit_source``. ``.py`` not under any root are skipped.
        """
        from llama_index.core.schema import TextNode

        doc_suffixes = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
        doc_paths = [p for p in paths if Path(p).suffix.lower() in doc_suffixes]
        plain_paths = [p for p in paths if Path(p).suffix.lower() in _PLAIN_TEXT_SUFFIXES]
        py_paths = [p for p in paths if Path(p).suffix.lower() == ".py"]
        wf_paths = [p for p in paths if Path(p).suffix.lower() == ".json"]

        docs = self.add_documents_from_paths(doc_paths)
        docs.extend(self.add_plain_text_from_paths(plain_paths))
        if unit_source_roots:
            docs.extend(self._docs_from_unit_py_paths(py_paths, unit_source_roots))
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
        Look up a node (catalogue entry) by id from the RAG index.
        Returns metadata dict or None if not found.
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

    def get_by_file_path(self, file_path: str) -> list[dict[str, Any]]:
        """
        Retrieve all chunks from the index whose metadata file_path equals the given path.
        Used for read_file action: get full indexed content for a file by path.
        Returns list of {text, metadata, score} (score is 1.0 for path-based retrieval).
        Path is normalized to absolute for matching (index stores absolute paths).
        """
        path_str = (file_path or "").strip()
        if not path_str:
            return []
        result = None
        try:
            resolved = str(Path(path_str).resolve())
            coll = self._get_chroma_collection()
            result = coll.get(
                where={"file_path": {"$eq": resolved}},
                include=["documents", "metadatas"],
            )
        except Exception:
            result = None
        if (not result or not result.get("ids")):
            try:
                coll = self._get_chroma_collection()
                result = coll.get(
                    where={"file_path": {"$eq": path_str}},
                    include=["documents", "metadatas"],
                )
            except Exception:
                result = None
        if not result or not result.get("ids"):
            return []
        docs = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        # Chroma may return documents as list of lists for multi-embedding; take first element if so
        out: list[dict[str, Any]] = []
        for i, meta in enumerate(metadatas):
            text = ""
            if i < len(docs):
                d = docs[i]
                text = d[0] if isinstance(d, (list, tuple)) and d else (d if isinstance(d, str) else str(d))
            out.append({
                "text": text or "",
                "metadata": meta if isinstance(meta, dict) else {},
                "score": 1.0,
            })
        return out

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
