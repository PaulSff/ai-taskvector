"""
RAG index orchestrator: run upload, search, and delete workflows.

All read/write operations are executed through workflow JSON files — no unit modules
are imported directly.  The workflow executor drives the appropriate units internally:

  - **Write/index** → ``rag/workflows/rag_upload_pipeline.json``  (ChromaIndexer + Embedder)
  - **Search**      → ``rag/workflows/rag_raw_search.json``        (RagSearch)
  - **Delete**      → ``rag/workflows/rag_delete_from_index.json`` (DeleteFromIndex)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence


def _repo_root() -> Path:
    """Absolute path to the repository root (parent of ``rag/``)."""
    return Path(__file__).resolve().parent.parent


def _default_rag_embedding_model() -> str:
    """Default embedding model: from settings when available."""
    try:
        from gui.components.settings import get_rag_embedding_model

        return get_rag_embedding_model()
    except ImportError:
        return "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


class RAGIndex:
    """
    Orchestrate RAG index operations over workflows, nodes, and documents.

    All Chroma/embedding logic is encapsulated in the respective workflow units;
    this class only drives workflows and manages the persist_dir / embedding_model
    parameters that are passed into those workflows as overrides.
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
        self._index = True  # sentinel kept for callers that check ``index._index``

    @property
    def _downloads_dir(self) -> Path:
        """Persistent directory for files fetched from remote URLs.

        Reads ``rag_downloads_dir`` from ragconf (default: ``mydata/rag/downloads``).
        Relative paths are resolved from the repo root. Falls back to
        ``persist_dir/../downloads`` if the config cannot be read.
        """
        try:
            from rag.ragconf_loader import rag_downloads_dir_raw

            raw = rag_downloads_dir_raw()
            d = Path(raw)
            if not d.is_absolute():
                d = _repo_root() / d
        except Exception:
            d = self.persist_dir.parent / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Write / index — driven by rag_upload_pipeline.json
    # ------------------------------------------------------------------

    def _run_upload_pipeline(self, source: str | Path) -> int:
        """
        Run ``rag_upload_pipeline.json`` for a single source (local path or URL).

        The pipeline handles fetching, extraction, chunking, embedding, and Chroma
        writes internally.  Returns the number of chunks indexed, or 0 on failure.
        """
        from rag.ragconf_loader import rag_upload_pipeline_workflow_path_raw
        from runtime.run import run_workflow

        wf_path = _repo_root() / rag_upload_pipeline_workflow_path_raw()
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
        """Scan directory for JSON files and index each through the upload pipeline."""
        root = Path(dir_path)
        if not root.is_dir():
            return 0
        count = 0
        for path in root.rglob("*.json"):
            count += self._run_upload_pipeline(path)
        return count

    def add_workflows_from_paths(self, paths: list[str | Path]) -> int:
        """Index JSON files from an explicit list through the upload pipeline."""
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
            path_iter = paths  # type: ignore[assignment]
        for p in path_iter:
            path = Path(p)
            if path.is_file() and path.suffix.lower() == ".json":
                count += self._run_upload_pipeline(path)
        return count

    def add_nodes_from_catalogue_file(self, path: str | Path) -> int:
        """Index a Node-RED catalogue JSON file through the upload pipeline."""
        p = Path(path)
        if not p.is_file():
            return 0
        return self._run_upload_pipeline(p)

    def add_chat_history_from_json(
        self, path: str | Path, source: str | None = None
    ) -> int:
        """Index a chat history JSON file through the upload pipeline."""
        p = Path(path)
        if not p.is_file() or p.suffix.lower() != ".json":
            return 0
        return self._run_upload_pipeline(p)

    def add_from_url_and_index(self, url: str) -> int:
        """Fetch a URL and add to the index via the upload pipeline."""
        return self._run_upload_pipeline(url)

    def add_documents_and_index(
        self,
        paths: Sequence[str | Path],
        *,
        workflows_dir: str | Path | None = None,
        unit_source_roots: Sequence[str | Path] | None = None,
        repo_root_for_agents_utf8: Path | None = None,
        rag_units_dir: str | Path | None = None,
        rag_mydata_dir: str | Path | None = None,
    ) -> int:
        """Index files through the upload pipeline. All file types are routed by the pipeline."""
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
        """Build the full index from workflows and/or a node catalogue."""
        count = 0
        if workflows_dir:
            count += self.add_workflows_from_dir(workflows_dir)
        if nodes_catalogue_file:
            count += self.add_nodes_from_catalogue_file(nodes_catalogue_file)
        if not count:
            raise ValueError(
                "No documents to index. Provide at least one of "
                "workflows_dir or nodes_catalogue_file."
            )

    # ------------------------------------------------------------------
    # Delete — driven by rag_delete_from_index.json
    # ------------------------------------------------------------------

    def delete_by_file_paths(self, file_paths: list[str]) -> int:
        """
        Remove from the index all chunks whose ``metadata.file_path`` is in ``file_paths``.
        Returns the total number of chunk IDs deleted (via DeleteFromIndex unit), or 0 on error.
        Used for incremental index updates (delete then re-index changed files).
        """
        if not file_paths:
            return 0
        from rag.ragconf_loader import rag_delete_from_index_workflow_path_raw
        from runtime.run import run_workflow

        wf_path = _repo_root() / rag_delete_from_index_workflow_path_raw()
        if not wf_path.is_file():
            return 0
        try:
            outputs = run_workflow(
                wf_path,
                initial_inputs={"inject_paths": {"data": file_paths}},
                unit_param_overrides={
                    "delete_idx": {"persist_dir": str(self.persist_dir)},
                },
                execution_timeout_s=60.0,
            )
        except Exception:
            return 0
        result = (outputs or {}).get("delete_idx", {})
        return int(result.get("count", 0) or 0) if isinstance(result, dict) else 0

    # ------------------------------------------------------------------
    # Search / retrieval — driven by rag_raw_search.json
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        content_type: str | None = None,
        metadata_file_path_contains: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search the index via workflow. Returns list of {text, metadata, score}.
        Runs rag_raw_search.json with the query wired to RagSearch.
        """
        from rag.search import search as _search

        return _search(
            query,
            persist_dir=str(self.persist_dir),
            embedding_model=self.embedding_model,
            top_k=top_k,
            content_type=content_type,
            metadata_file_path_contains=metadata_file_path_contains,
        )

    def get_by_file_path(self, file_path: str) -> list[dict[str, Any]]:
        """
        Retrieve all indexed chunks for the given file path via workflow.
        Returns list of {text, metadata, score} (score 1.0 for path match).
        """
        from rag.search import get_by_file_path as _get_by_file_path

        return _get_by_file_path(
            file_path,
            persist_dir=str(self.persist_dir),
            embedding_model=self.embedding_model,
        )
