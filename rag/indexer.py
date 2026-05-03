"""
RAG index builder: workflows, nodes, and user documents.
Uses ChromaDB + sentence-transformers (``Embedder`` / ``ChromaIndexer`` units under ``units/rag/``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, NamedTuple, Sequence

from rag.content_types import (
    content_type_for_indexed_file,
    content_type_for_markdown_file,
    repo_relative_posix,
)
from rag.search import (
    get_by_file_path as _rag_get_by_file_path,
    get_chroma_collection,
    get_node_by_id as _rag_get_node_by_id,
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


# Plain-text formats: read as UTF-8 (no Docling). Must match rag.context_updater.RAG_PLAIN_TEXT_SUFFIXES.
_PLAIN_TEXT_SUFFIXES = {
    ".csv",
    ".txt",
    ".yaml",
    ".yml",
    ".xml",
    ".log",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".tsv",
    ".rst",
}
_MAX_PLAIN_TEXT_CHARS = 50000


def _path_is_under(path: Path, root: Path) -> bool:
    """True if ``path`` is ``root`` or nested under ``root``."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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
_DOC_TO_TEXT_WORKFLOW_REL = "rag/workflows/doc_to_text.json"


def _get_doc_to_text_workflow_path() -> Path:
    """Path to doc_to_text workflow from ``rag/ragconf.yaml`` (via ``get_doc_to_text_workflow_path``)."""
    try:
        from gui.components.settings import get_doc_to_text_workflow_path

        return get_doc_to_text_workflow_path()
    except ImportError:
        pass
    root = Path(__file__).resolve().parent.parent
    return root / _DOC_TO_TEXT_WORKFLOW_REL


_UPLOAD_PIPELINE_REL = "rag/workflows/rag_upload_pipeline.json"


def _get_upload_pipeline_path() -> Path:
    """Path to rag_upload_pipeline.json (full injection + indexing pipeline)."""
    root = Path(__file__).resolve().parent.parent
    return root / _UPLOAD_PIPELINE_REL


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
        """Persistent directory for files fetched from remote URLs."""
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

    def add_documents_from_dir(self, dir_path: str | Path) -> list[Any]:
        """Parse PDF, DOC, XLS in directory via doc_to_text workflow (Docling + pandas tables). Skips files when workflow returns no text."""
        docs: list[Any] = []
        root = Path(dir_path)
        if not root.is_dir():
            return docs

        suffixes = {
            ".pdf",
            ".docx",
            ".doc",
            ".xlsx",
            ".xls",
            ".pptx",
            ".ppt",
            ".html",
            ".md",
        }
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
            doc = _rag_chunk(text[:50000], meta)
            docs.append(doc)
        return docs

    def add_documents_from_paths(
        self,
        paths: list[str | Path],
        *,
        repo_root_for_content_types: Path | None = None,
        rag_units_dir: str | Path | None = None,
        rag_mydata_dir: str | Path | None = None,
    ) -> list[Any]:
        """Parse specific files via doc_to_text workflow (Docling + pandas tables). Skips files when workflow returns no text."""
        docs: list[Any] = []
        suffixes = {
            ".pdf",
            ".docx",
            ".doc",
            ".xlsx",
            ".xls",
            ".pptx",
            ".ppt",
            ".html",
            ".md",
        }
        ru = Path(rag_units_dir).resolve() if rag_units_dir is not None else None
        rm = Path(rag_mydata_dir).resolve() if rag_mydata_dir is not None else None
        rr = (
            repo_root_for_content_types.resolve()
            if repo_root_for_content_types is not None
            else None
        )
        try:
            from tqdm import tqdm

            path_iter = tqdm(
                paths,
                desc="RAG documents",
                unit="file",
                leave=False,
                disable=not sys.stdout.isatty(),
            )
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
            suf = path.suffix.lower()
            if rr is not None:
                ct = content_type_for_indexed_file(
                    rr, path, suffix=suf, fallback="document"
                )
                rel = repo_relative_posix(rr, path)
                src = rel if rel is not None else path.name
            elif suf == ".md" and (ru is not None or rm is not None):
                ct = content_type_for_markdown_file(
                    path, rag_units_dir=ru, rag_mydata_dir=rm
                )
                src = path.name
            else:
                ct = "document"
                src = path.name
            meta = {
                "content_type": ct,
                "source": src,
                "file_path": str(path.absolute()),
            }
            doc = _rag_chunk(text[:50000], meta)
            docs.append(doc)
        return docs

    def add_plain_text_from_paths(
        self,
        paths: list[str | Path],
        *,
        repo_root_for_content_types: Path | None = None,
    ) -> list[Any]:
        """Index plain-text files (CSV, TXT, YAML, etc.) by reading as UTF-8. No Docling."""
        docs: list[Any] = []
        try:
            from tqdm import tqdm

            path_iter = tqdm(
                paths,
                desc="RAG plain text",
                unit="file",
                leave=False,
                disable=not sys.stdout.isatty(),
            )
        except ImportError:
            path_iter = paths
        rr = (
            repo_root_for_content_types.resolve()
            if repo_root_for_content_types is not None
            else None
        )
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
            suf = path.suffix.lower()
            rel = repo_relative_posix(rr, path) if rr is not None else None
            ct = (
                content_type_for_indexed_file(rr, path, suffix=suf, fallback="document")
                if rr is not None
                else "document"
            )
            meta = {
                "content_type": ct,
                "source": rel if rel is not None else path.name,
                "file_path": str(path.absolute()),
            }
            docs.append(_rag_chunk(text, meta))
        return docs

    def add_assistants_rag_utf8_documents(
        self,
        paths: Sequence[str | Path],
        *,
        repo_root: Path,
    ) -> list[Any]:
        """
        Index ``assistants/**/*.md`` and ``assistants/**/*.py`` as UTF-8 (no Docling).
        Embeds repo-relative path in the chunk text so RAG matches paths and titles.
        """
        docs: list[Any] = []
        rr = repo_root.resolve()
        assistants_root = rr / "assistants"
        if not assistants_root.is_dir():
            return docs
        try:
            from tqdm import tqdm

            path_iter = tqdm(
                list(paths),
                desc="RAG assistants docs",
                unit="file",
                leave=False,
                disable=not sys.stdout.isatty(),
            )
        except ImportError:
            path_iter = paths
        for raw in path_iter:
            path = Path(raw)
            if not path.is_file():
                continue
            if not _path_is_under(path, assistants_root):
                continue
            suf = path.suffix.lower()
            if suf not in {".md", ".py"}:
                continue
            if "encrypted" in path.name.lower():
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if not body:
                continue
            try:
                rel = str(path.resolve().relative_to(rr)).replace("\\", "/")
            except ValueError:
                rel = path.name
            prefix = f"Assistants documentation ({rel}):\n\n"
            text = (prefix + body)[:_MAX_PLAIN_TEXT_CHARS]
            meta = {
                "content_type": content_type_for_indexed_file(
                    rr, path, suffix=suf, fallback="document"
                ),
                "source": rel,
                "file_path": str(path.resolve()),
            }
            docs.append(_rag_chunk(text, meta))
        return docs

    def _docs_from_unit_py_paths(
        self,
        paths: list[str | Path],
        unit_source_roots: Sequence[str | Path],
        *,
        repo_root_for_content_types: Path | None = None,
    ) -> list[Any]:
        """Index .py under unit_source_roots as UTF-8 plain text (``taskvector_units_source`` when under repo)."""
        docs: list[Any] = []
        if not unit_source_roots:
            return docs
        rr = (
            repo_root_for_content_types.resolve()
            if repo_root_for_content_types is not None
            else None
        )
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
            ct = content_type_for_indexed_file(
                rr, path, suffix=".py", fallback="taskvector_units_source"
            )
            meta = {
                "content_type": ct,
                "source": rel,
                "file_path": str(path.resolve()),
            }
            docs.append(_rag_chunk(text, meta))
        return docs

    def add_from_url_and_index(self, url: str) -> int:
        """
        Fetch from URL and add to index.

        Delegates to ``_run_upload_pipeline`` which passes the URL through
        ``FetchSource`` (downloads to ``_downloads_dir``) and then runs the
        full extraction + embedding + Chroma pipeline.

        For non-JSON documents (PDF, DOCX, …) that are not yet handled by
        ``rag_upload_pipeline.json`` routing, the method falls back to a
        temp-file download + ``add_documents_and_index``.
        """
        import tempfile

        import requests

        # Probe the content-type first so we can decide which path to take
        # without downloading the whole file twice.
        try:
            head = requests.head(url, timeout=15, allow_redirects=True)
            ct = (head.headers.get("content-type") or "").lower()
        except Exception:
            ct = ""

        if "json" in ct or url.rstrip("/").endswith(".json"):
            # JSON: FetchSource downloads + full pipeline handles extraction
            return self._run_upload_pipeline(url)

        # Non-JSON document — download to temp file and index via doc_to_text workflow
        suffix = Path(url.split("?")[0]).suffix.lower() or ".bin"
        if suffix not in {
            ".pdf",
            ".docx",
            ".doc",
            ".xlsx",
            ".xls",
            ".pptx",
            ".ppt",
            ".html",
            ".md",
        }:
            raise ValueError(f"Unsupported document type: {suffix}")
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch URL: {e}") from e
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(r.content)
            tmp_path = f.name
        try:
            return self.add_documents_and_index([tmp_path])
        finally:
            Path(tmp_path).unlink(missing_ok=True)

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
        as UTF-8 with ``content_type`` from :mod:`rag.content_types` (e.g. ``taskvector_units_source``).

        repo_root_for_assistants_utf8: when set, used as the TaskVector repo root for ``content_type``
        on all indexed files under that root; ``.md`` / ``.py`` under ``assistants/`` are read as
        UTF-8 (no Docling).

        rag_units_dir / rag_mydata_dir: when no repo root is passed, Docling-backed ``.md`` under
        those roots still get ``unit_readme`` / ``taskvector_units_readme`` vs ``document`` (mydata).
        """
        doc_suffixes = {
            ".pdf",
            ".docx",
            ".doc",
            ".xlsx",
            ".xls",
            ".pptx",
            ".ppt",
            ".html",
            ".md",
        }
        assistants_root: Path | None = None
        content_rr: Path | None = None
        if repo_root_for_assistants_utf8 is not None:
            content_rr = Path(repo_root_for_assistants_utf8).resolve()
            ar = content_rr / "assistants"
            if ar.is_dir():
                assistants_root = ar

        doc_paths: list[str | Path] = []
        plain_paths: list[str | Path] = []
        py_paths: list[str | Path] = []
        wf_paths: list[str | Path] = []
        assistants_utf8: list[Path] = []

        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                continue
            pr = path.resolve()
            suf = path.suffix.lower()
            if (
                assistants_root is not None
                and _path_is_under(pr, assistants_root)
                and suf in {".md", ".py"}
            ):
                assistants_utf8.append(pr)
                continue
            if suf in doc_suffixes:
                doc_paths.append(raw)
            elif suf in _PLAIN_TEXT_SUFFIXES:
                plain_paths.append(raw)
            elif suf == ".py":
                py_paths.append(raw)
            elif suf == ".json":
                wf_paths.append(raw)

        docs = self.add_documents_from_paths(
            doc_paths,
            repo_root_for_content_types=content_rr,
            rag_units_dir=rag_units_dir,
            rag_mydata_dir=rag_mydata_dir,
        )
        docs.extend(
            self.add_plain_text_from_paths(
                plain_paths, repo_root_for_content_types=content_rr
            ),
        )
        if unit_source_roots:
            docs.extend(
                self._docs_from_unit_py_paths(
                    py_paths,
                    unit_source_roots,
                    repo_root_for_content_types=content_rr,
                ),
            )
        json_count = 0
        for p in wf_paths:
            json_count += self._run_upload_pipeline(Path(p))
        if assistants_utf8 and repo_root_for_assistants_utf8 is not None:
            docs.extend(
                self.add_assistants_rag_utf8_documents(
                    assistants_utf8,
                    repo_root=Path(repo_root_for_assistants_utf8),
                )
            )
        if not docs and json_count == 0:
            return 0
        non_json_count = 0
        if docs:
            try:
                self._load_index()
                non_json_count = self._upsert_chunks(docs)
            except Exception:
                self._build_index(docs)
                non_json_count = len(docs)
        return json_count + non_json_count

    def build(
        self,
        *,
        workflows_dir: str | Path | None = None,
        nodes_catalogue_file: str | Path | None = None,
        docs_dir: str | Path | None = None,
    ) -> None:
        """Build the full index from workflows, nodes, and documents."""
        count = 0

        if workflows_dir:
            count += self.add_workflows_from_dir(workflows_dir)

        if nodes_catalogue_file:
            count += self.add_nodes_from_catalogue_file(nodes_catalogue_file)

        if docs_dir:
            doc_docs = self.add_documents_from_dir(docs_dir)
            if doc_docs:
                self._upsert_chunks(doc_docs)
                count += len(doc_docs)

        if not count:
            raise ValueError(
                "No documents to index. Provide at least one of workflows_dir, nodes_catalogue_file, or docs_dir."
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
