"""
RAG index orchestrator: run upload, search, and delete workflows.

All read/write operations are executed through workflow JSON files — no unit modules
are imported directly.  The workflow executor drives the appropriate units internally:

  - **Write/index** → ``rag/workflows/rag_upload_pipeline.json``  (ChromaIndexer + Embedder)
  - **Search**      → ``rag/workflows/rag_raw_search.json``        (RagSearch)
  - **Delete**      → ``rag/workflows/rag_delete_from_index.json`` (DeleteFromIndex)
"""

from __future__ import annotations

import asyncio
import re
import threading
import sys
from pathlib import Path
from typing import Any, Sequence, Callable, cast

from rag.index_workflow_handler import WorkflowServerClient
from rag.ragconf_loader import (
    rag_index_workflow_server_endpoint_raw,
    rag_index_response_endpoint_raw,
    rag_index_response_timeout_s_raw,
)
from rag.ragconf_loader import rag_index_max_parallel_uploads_raw

RESPONSE_TIMEOUT_S = rag_index_response_timeout_s_raw()
LOOP_TIMEOUT = 10

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
WORKFLOW_SERVER_ENDPOINT = rag_index_workflow_server_endpoint_raw()  # e.g. tcp://127.0.0.1:6679
RAG_INDEX_RESPONSE_ENDPOINT = rag_index_response_endpoint_raw()      # e.g. tcp://127.0.0.1:xxxx

N = rag_index_max_parallel_uploads_raw()

def _parse_host_port(endpoint: str) -> tuple[str, int]:
    # "tcp://127.0.0.1:6679" -> ("tcp://127.0.0.1", 6679)
    m = re.match(r"^(.*):(\d+)$", endpoint)
    if not m:
        raise ValueError(f"Unexpected endpoint format: {endpoint}")
    return m.group(1), int(m.group(2))

workflow_host, workflow_port = _parse_host_port(WORKFLOW_SERVER_ENDPOINT)
resp_host, resp_port = _parse_host_port(RAG_INDEX_RESPONSE_ENDPOINT)

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
JOB_PUB_ENDPOINTS = [f"{workflow_host}:{workflow_port + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"{resp_host}:{resp_port + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS

# ---- internal slot allocator (no slot in public APIs) ----
_slot_sem = asyncio.Semaphore(N)
_slot_next = 0
_slot_lock = asyncio.Lock()


async def _acquire_slot() -> int:
    global _slot_next
    await _slot_sem.acquire()
    async with _slot_lock:
        slot = _slot_next
        _slot_next = (_slot_next + 1) % N
    return slot


async def _release_slot() -> None:
    _slot_sem.release()


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
        self.embedding_model = (embedding_model or _default_rag_embedding_model()).strip()

        self._index = True  # sentinel kept for callers that check ``index._index``

        # Background loop used for parallel upload coroutines
        self._bg_loop: asyncio.AbstractEventLoop | None = None
        self._bg_thread: "threading.Thread | None" = None

        # One workflow client per endpoint-slot (so concurrent calls don't share endpoints)
        self._upload_clients: list[WorkflowServerClient | None] = [None] * N
        self._upload_clients_closed: list[bool] = [False] * N
        self._upload_client_init_locks: list[asyncio.Lock] = [asyncio.Lock() for _ in range(N)]

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

        Returns:
        - number of chunks indexed, or 0 on failure.
        """
        from rag.ragconf_loader import rag_upload_pipeline_workflow_path_raw

        import threading

        wf_path = _repo_root() / rag_upload_pipeline_workflow_path_raw()
        if not wf_path.is_file():
            return 0

        src = str(source) if isinstance(source, Path) else source

        async def _async_call() -> int:
            slot = await _acquire_slot()
            try:
                # Create/reuse a client *per slot* (so endpoint pairs match)
                async with self._upload_client_init_locks[slot]:
                    if self._upload_clients[slot] is None or self._upload_clients_closed[slot]:
                        self._upload_clients[slot] = WorkflowServerClient(
                            pub_endpoint=JOB_PUB_ENDPOINTS[slot],
                            sub_endpoint=RESPONSE_SUB_ENDPOINTS[slot],
                            response_timeout_s=RESPONSE_TIMEOUT_S,
                        )
                        self._upload_clients_closed[slot] = False

                client = self._upload_clients[slot]
                assert client is not None

                try:
                    print(
                        f"RAG INFO: _run_upload_pipeline start indexing src={src} slot={slot}",
                        flush=True,
                    )

                    out = await client.run(
                        workflow_path=str(wf_path),
                        initial_inputs={"inject_path": {"data": src}},
                        unit_param_overrides={
                            "fetch_source": {"save_dir": str(self._downloads_dir)},
                            "chroma": {
                                "persist_dir": str(self.persist_dir),
                                "embedding_model": self.embedding_model,
                            },
                            "emb": {"model_name": self.embedding_model},
                        },
                        format=None,
                    )

                    print(
                        f"RAG INFO: _run_upload_pipeline returned src={src} slot={slot}",
                        flush=True,
                    )

                    if not isinstance(out, dict) or "error" in out:
                        return 0

                    outputs = out.get("result", {}) or {}
                    chroma_out = (outputs or {}).get("chroma", {}) or {}
                    if not isinstance(chroma_out, dict):
                        return 0

                    return int(chroma_out.get("count", 0) or 0)

                except Exception as e:
                    print(
                        f"RAG ERROR: upload pipeline failed (src={src}, slot={slot}): "
                        f"{type(e).__name__}: {e}",
                        flush=True,
                    )
                    return 0

            finally:
                await _release_slot()

        # Ensure we have a single background loop running
        if self._bg_loop is None or self._bg_thread is None or not self._bg_thread.is_alive():
            loop_ready = threading.Event()

            def _thread_main():
                bg_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(bg_loop)
                self._bg_loop = bg_loop
                loop_ready.set()
                bg_loop.run_forever()

            self._bg_thread = threading.Thread(target=_thread_main, daemon=True)
            self._bg_thread.start()
            loop_ready.wait(timeout=10)

        assert self._bg_loop is not None

        # Submit coroutine to the dedicated background loop and block for its result
        fut = asyncio.run_coroutine_threadsafe(_async_call(), self._bg_loop)
        try:
            return fut.result()
        except Exception as e:
            print(
                f"RAG ERROR: _run_upload_pipeline wrapper failed (src={src}): "
                f"{type(e).__name__}: {e}",
                flush=True,
            )
            return 0


    def add_workflows_from_dir(self, dir_path: str | Path) -> int:
        root = Path(dir_path)
        if not root.is_dir():
            return 0
        paths = [p for p in root.rglob("*.json")]
        return self.add_sources_parallel(paths)


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
        file_sources: list[str | Path] = [Path(raw) for raw in paths if Path(raw).is_file()]

        count: int = 0

        add_sources_parallel = getattr(self, "add_sources_parallel", None)
        add_sources_parallel_fn: Callable[[list[str | Path]], int] | None = (
            cast(Callable[[list[str | Path]], int] | None, add_sources_parallel)
            if callable(add_sources_parallel)
            else None
        )

        if add_sources_parallel_fn is not None and file_sources:
            count += add_sources_parallel_fn(file_sources)
        else:
            for src in file_sources:
                count += self._run_upload_pipeline(src)

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

    # --------- Parallel uploading ----------
    def _ensure_bg_loop(self) -> None:

        bg_loop = getattr(self, "_bg_loop", None)
        bg_thread = getattr(self, "_bg_thread", None)

        if bg_loop is not None and bg_thread is not None and bg_thread.is_alive():
            return

        loop_ready = threading.Event()

        def _thread_main():
            bg_loop_inner = asyncio.new_event_loop()
            asyncio.set_event_loop(bg_loop_inner)
            self._bg_loop = bg_loop_inner
            loop_ready.set()
            bg_loop_inner.run_forever()

        self._bg_thread = threading.Thread(target=_thread_main, daemon=True)
        self._bg_thread.start()
        loop_ready.wait(timeout=LOOP_TIMEOUT)

        if self._bg_loop is None:
            raise RuntimeError("Failed to start background event loop")

    def _rag_index_max_concurrencies(self) -> int:
        try:

            v = int(rag_index_max_parallel_uploads_raw())
            return max(1, v)
        except Exception:
            return 4

    async def _upload_one_async(self, source: str | Path) -> int:
        from rag.ragconf_loader import rag_upload_pipeline_workflow_path_raw

        def _display_src(src: str | Path) -> str:
            p = Path(src)
            parts = p.parts
            if len(parts) >= 2:
                tail = Path(*parts[-2:]).as_posix()  # e.g. "something/filename.py"
                return f"../{tail}"
            if len(parts) == 1:
                return parts[0]
            return str(src)

        wf_path = _repo_root() / rag_upload_pipeline_workflow_path_raw()
        if not wf_path.is_file():
            return 0

        src = str(source) if isinstance(source, Path) else source

        slot = await _acquire_slot()
        print(
            f"RAG INFO: _upload_one_async start indexing src={_display_src(src)} slot={slot}",
            flush=True,
        )

        try:
            # Create/reuse one client per slot (so concurrent calls don't share endpoints)
            async with self._upload_client_init_locks[slot]:
                if self._upload_clients[slot] is None or self._upload_clients_closed[slot]:
                    self._upload_clients[slot] = WorkflowServerClient(
                        pub_endpoint=JOB_PUB_ENDPOINTS[slot],
                        sub_endpoint=RESPONSE_ENDPOINTS[slot],
                        response_timeout_s=RESPONSE_TIMEOUT_S,
                    )
                    self._upload_clients_closed[slot] = False

            client = self._upload_clients[slot]
            assert client is not None

            out = await client.run(
                workflow_path=str(wf_path),
                initial_inputs={"inject_path": {"data": src}},
                unit_param_overrides={
                    "fetch_source": {"save_dir": str(self._downloads_dir)},
                    "chroma": {
                        "persist_dir": str(self.persist_dir),
                        "embedding_model": self.embedding_model,
                    },
                    "emb": {"model_name": self.embedding_model},
                },
                format=None,
            )

            if not isinstance(out, dict) or "error" in out:
                return 0

            outputs = out.get("result", {}) or {}
            chroma_out = (outputs or {}).get("chroma", {}) or {}
            if not isinstance(chroma_out, dict):
                return 0

            return int(chroma_out.get("count", 0) or 0)

        except Exception as e:
            print(
                f"RAG ERROR: upload failed (src={_display_src(src)}, slot={slot}): "
                f"{type(e).__name__}: {e}",
                flush=True,
            )
            return 0

        finally:
            await _release_slot()


    def add_sources_parallel(
        self,
        sources: Sequence[str | Path],
        *,
        max_concurrency: int | None = None,
    ) -> int:
        self._ensure_bg_loop()

        if max_concurrency is None:
            max_concurrency = self._rag_index_max_concurrencies()

        max_concurrency = max(1, int(max_concurrency))
        # IMPORTANT: don’t let callers exceed the number of endpoint slots (N)
        max_concurrency = min(max_concurrency, len(JOB_PUB_ENDPOINTS))

        async def _main() -> int:
            sem = asyncio.Semaphore(max_concurrency)

            async def _one(src: str | Path) -> int:
                async with sem:
                    return await self._upload_one_async(src)

            tasks = [asyncio.create_task(_one(s)) for s in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            total = 0
            for r in results:
                if isinstance(r, int):
                    total += r
            return total

        bg_loop = self._bg_loop
        if bg_loop is None:
            raise RuntimeError("Background event loop not initialized")

        fut = asyncio.run_coroutine_threadsafe(_main(), bg_loop)
        return fut.result()


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

    async def close(self) -> None:
        for i, client in enumerate(self._upload_clients):
            if client is not None and not self._upload_clients_closed[i]:
                await client.close()
                self._upload_clients_closed[i] = True
