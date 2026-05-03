"""
RAG index builder: workflows, nodes, and user documents.
Uses ChromaDB + sentence-transformers (``Embedder`` / ``ChromaIndexer`` units under ``units/rag/``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, NamedTuple, Sequence

from rag.search import (
    get_by_file_path as _rag_get_by_file_path,
)
from rag.search import (
    get_chroma_collection,
)
from rag.search import (
    get_node_by_id as _rag_get_node_by_id,
)
from rag.search import (
    search_index as _rag_search_index,
)
from units.rag.chroma_indexer.chroma_indexer import (
    add_rag_chunks,
    chroma_safe_metadata,
    rebuild_rag_collection,
)


class RAGChunk(NamedTuple):
    """One searchable row: text body + Chroma-safe metadata (replaces LlamaIndex ``Document``)."""

    text: str
    metadata: dict[str, Any]


_UPLOAD_PIPELINE_REL = "rag/workflows/rag_upload_pipeline.json"


def _get_upload_pipeline_path() -> Path:
    """Path to rag_upload_pipeline.json (full injection + indexing pipeline)."""
    root = Path(__file__).resolve().parent.parent
    return root / _UPLOAD_PIPELINE_REL


def _rag_chunk(text: str, metadata: dict[str, Any]) -> RAGChunk:
    return RAGChunk(text=text, metadata=chroma_safe_metadata(metadata))


def _default_rag_embedding_model() -> str:
    """Default embedding model: from settings when available."""
    try:
        from gui.components.settings import get_rag_embedding_model

        return get_rag_embedding_model()
    except ImportError:
        return "sentence-transformers/all-MiniLM-L6-v2"


def _prepare_hf_offline_env() -> None:
    import os

    from rag.ragconf_loader import rag_offline_raw

    if rag_offline_raw():
        os.environ["HF_HUB_OFFLINE"] = "1"


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
        self.embedding_model = (
            embedding_model or _default_rag_embedding_model()
        ).strip()
        self._index = True  # sentinel: Chroma store is opened on demand; kept for callers checking ``index._index``

    def _chunks_as_pairs(
        self, chunks: list[RAGChunk]
    ) -> list[tuple[str, dict[str, Any]]]:
        return [(c.text, dict(c.metadata)) for c in chunks]

    def _build_index(self, documents: list[RAGChunk]) -> None:
        if documents:
            print(
                f"RAG: Building vector index ({len(documents)} chunk(s))...", flush=True
            )
        _prepare_hf_offline_env()
        rebuild_rag_collection(
            persist_dir=self.persist_dir,
            embedding_model=self.embedding_model,
            chunks=self._chunks_as_pairs(documents),
        )

    def _load_index(self) -> None:
        """Compatibility hook: Chroma collection is opened per operation; no LlamaIndex vector index."""
        _prepare_hf_offline_env()
        return None

    def _upsert_chunks(self, chunks: list[RAGChunk]) -> int:
        _prepare_hf_offline_env()
        return add_rag_chunks(
            persist_dir=self.persist_dir,
            embedding_model=self.embedding_model,
            chunks=self._chunks_as_pairs(chunks),
        )

    @property
    def _downloads_dir(self) -> Path:
        """Persistent directory for files fetched from remote URLs.

        Reads ``rag_downloads_dir`` from ragconf (default: ``mydata/rag/downloads``).
        Relative paths are resolved from the repo root so the directory lands inside
        mydata and is visible in the file manager. Falls back to
        ``persist_dir/../downloads`` if the config cannot be read.
        """
        try:
            from rag.ragconf_loader import rag_downloads_dir_raw

            raw = rag_downloads_dir_raw()
            d = Path(raw)
            if not d.is_absolute():
                # Resolve relative to repo root (parent of rag/)
                repo_root = Path(__file__).resolve().parent.parent
                d = repo_root / d
        except Exception:
            d = self.persist_dir.parent / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _run_upload_pipeline(self, source: str | Path) -> int:
        """
        Run rag_upload_pipeline.json for a single source (local file path or remote URL).

        FetchSource resolves the source to a local file before the rest of the pipeline
        runs.  The workflow handles extraction, chunking, embedding, and Chroma writes
        internally.  Returns the number of chunks indexed, or 0 on failure.
        """
        from runtime.run import run_workflow

        wf_path = _get_upload_pipeline_path()
        if not wf_path.is_file():
            return 0
        src = str(source) if isinstance(source, Path) else source
        try:
            outputs = run_workflow(
                wf_path,
                initial_inputs={"inject_path": {"data": src}},
                unit_param_overrides={
                    "fetch_source": {"save_dir": str(self._downloads_dir)},
                    "chroma": {
                        "persist_dir": str(self.persist_dir),
                        "embedding_model": self.embedding_model,
                    },
                    "emb": {"model_name": self.embedding_model},
                },
                execution_timeout_s=120.0,
            )
        except Exception:
            return 0
        chroma_out = (outputs or {}).get("chroma", {})
        return (
            int(chroma_out.get("count", 0) or 0) if isinstance(chroma_out, dict) else 0
        )

    def add_workflows_from_dir(self, dir_path: str | Path) -> int:
        """Scan directory for JSON files and index each through rag_upload_pipeline.json."""
        root = Path(dir_path)
        if not root.is_dir():
            return 0
        count = 0
        for path in root.rglob("*.json"):
            count += self._run_upload_pipeline(path)
        return count

    def add_workflows_from_paths(self, paths: list[str | Path]) -> int:
        """Index JSON files from paths through rag_upload_pipeline.json."""
        count = 0
        try:
            from tqdm import tqdm

            path_iter = tqdm(
                paths,
                desc="RAG workflows",
                unit="file",
                leave=False,
                disable=not sys.stdout.isatty(),
            )
        except ImportError:
            path_iter = paths
        for p in path_iter:
            path = Path(p)
            if path.is_file() and path.suffix.lower() == ".json":
                count += self._run_upload_pipeline(path)
        return count

    def add_nodes_from_catalogue_file(self, path: str | Path) -> int:
        """Index a Node-RED catalogue JSON file through rag_upload_pipeline.json."""
        p = Path(path)
        if not p.is_file():
            return 0
        return self._run_upload_pipeline(p)

    def add_chat_history_from_json(
        self, path: str | Path, source: str | None = None
    ) -> int:
        """Index a chat history JSON file through rag_upload_pipeline.json."""
        p = Path(path)
        if not p.is_file() or p.suffix.lower() != ".json":
            return 0
        return self._run_upload_pipeline(p)

    def add_from_url_and_index(self, url: str) -> int:
        """Fetch from URL and add to index via rag_upload_pipeline.json."""
        return self._run_upload_pipeline(url)

    def add_documents_and_index(
        self,
        paths: Sequence[str | Path],
        *,
        workflows_dir: str | Path | None = None,
        unit_source_roots: Sequence[str | Path] | None = None,
        repo_root_for_assistants_utf8: Path | None = None,
        rag_units_dir: str | Path | None = None,
        rag_mydata_dir: str | Path | None = None,
    ) -> int:
        """Index files through rag_upload_pipeline.json. All file types are routed by the pipeline."""
        count = 0
        for raw in paths:
            path = Path(raw)
            if path.is_file():
                count += self._run_upload_pipeline(path)
        if workflows_dir:
            count += self.add_workflows_from_dir(workflows_dir)
        return count

    def build(
        self,
        *,
        workflows_dir: str | Path | None = None,
        nodes_catalogue_file: str | Path | None = None,
    ) -> None:
        """Build the full index from workflows and catalogues."""
        count = 0
        if workflows_dir:
            count += self.add_workflows_from_dir(workflows_dir)
        if nodes_catalogue_file:
            count += self.add_nodes_from_catalogue_file(nodes_catalogue_file)
        if not count:
            raise ValueError(
                "No documents to index. Provide at least one of workflows_dir or nodes_catalogue_file."
            )

    def delete_by_file_paths(self, file_paths: list[str]) -> int:
        """
        Remove from the index all nodes whose metadata file_path is in file_paths.
        Returns the number of file_paths that had at least one node removed (best effort).
        Used for incremental index updates (re-index only changed files).
        """
        if not file_paths:
            return 0
        try:
            coll = get_chroma_collection(self.persist_dir)
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
        return _rag_get_node_by_id(self, node_id)

    def get_by_file_path(self, file_path: str) -> list[dict[str, Any]]:
        """
        Retrieve all chunks from the index whose metadata file_path equals the given path.
        Used for read_file action: get full indexed content for a file by path.
        Returns list of {text, metadata, score} (score is 1.0 for path-based retrieval).
        Path is normalized to absolute for matching (index stores absolute paths).
        """
        return _rag_get_by_file_path(self, file_path)

    def search(
        self,
        query: str,
        top_k: int = 10,
        content_type: str | None = None,
        metadata_file_path_contains: str | None = None,
    ) -> list[dict]:
        """
        Search the index. Returns list of {text, metadata, score}.
        content_type: optional filter on ``metadata.content_type`` (see ``rag/search.py``).
        metadata_file_path_contains: optional substring matched against metadata ``file_path``
        (after normalizing ``\\`` to ``/``). When set, only matching chunks are returned; the
        retriever pulls extra candidates so similarity-ranked hits are still found (e.g. team
        member RAG doc vs. the rest of the index).
        """
        return _rag_search_index(
            self,
            query,
            top_k=top_k,
            content_type=content_type,
            metadata_file_path_contains=metadata_file_path_contains,
        )
