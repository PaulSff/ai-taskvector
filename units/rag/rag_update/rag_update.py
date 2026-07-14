"""
RagUpdate unit: run RAG index incremental update (units_dir + mydata_dir) via rag.context_updater.

Params: rag_index_data_dir (str), units_dir (str), mydata_dir (str), embedding_model (str, optional),
repo_root (str, optional). Use ``settings.<key>`` strings (resolved by the executor via ``app_settings_param``)
for paths and model, e.g. ``settings.rag_index_data_dir``, ``settings.mydata_dir``, ``settings.rag_embedding_model``.
When ``repo_root`` is omitted and ``rag_index_data_dir`` lies under the TaskVector repo, canonical ``*.json``
graphs across the repo are indexed; set ``repo_root`` explicitly (e.g. ``"."``) to override.

No input ports. Output: data (dict) with keys ok, need_index, units_count, mydata_count, repo_canonical_count, agents_rag_count, error, message, details.
Enables workflows (e.g. ``rag/workflows/rag_update.json``) to trigger index updates without direct context_updater calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import asyncio
from rag.context_updater import run_update
from units.registry import UnitSpec, register_unit

RAG_UPDATE_INPUT_PORTS: list[tuple[str, str]] = []
RAG_UPDATE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _repo_root() -> Path:
    """Repository root: ``units/rag/rag_update/rag_update.py`` → parents[3]."""
    return Path(__file__).resolve().parents[3]


def _resolve_under_repo(raw: str) -> Path:
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        p = _repo_root() / p
    return p.resolve()


def _rag_update_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call rag.context_updater.run_update.

    Behavior:
    - If a provided executor with .submit() exists, submit run_update to it and wait (blocks).
    - Otherwise, if a provided event loop exists via _executor_loop/_background_loop, schedule onto that loop
      and offload run_update to a worker thread using asyncio.to_thread, then wait (blocks).
    - Otherwise, run synchronously on the current thread.
    """

    rag_index_data_dir = (params.get("rag_index_data_dir") or "").strip()
    units_dir = (params.get("units_dir") or "").strip()
    mydata_dir = (params.get("mydata_dir") or "").strip()
    embedding_model = params.get("embedding_model")
    if embedding_model is not None and not isinstance(embedding_model, str):
        embedding_model = str(embedding_model)
    if embedding_model is not None:
        embedding_model = str(embedding_model).strip() or None

    if not rag_index_data_dir or not units_dir or not mydata_dir:
        err = "rag_index_data_dir, units_dir, and mydata_dir are required"
        bad = {
            "ok": False,
            "need_index": True,
            "units_count": 0,
            "mydata_count": 0,
            "repo_canonical_count": 0,
            "agents_rag_count": 0,
            "error": err,
            "message": err,
            "details": "missing params: "
            + ", ".join(
                p
                for p in ("rag_index_data_dir", "units_dir", "mydata_dir")
                if not (params.get(p) or "").strip()
            ),
        }
        return ({"data": bad, "error": err}, state)

    rag_index_data_dir = _resolve_under_repo(str(rag_index_data_dir))
    units_dir = _resolve_under_repo(str(units_dir))
    mydata_dir = _resolve_under_repo(str(mydata_dir))

    print("RagUpdate DEBUG resolved paths:", flush=True)
    print(f"  rag_index_data_dir: {rag_index_data_dir}", flush=True)
    print(f"  units_dir:         {units_dir}", flush=True)
    print(f"  mydata_dir:       {mydata_dir}", flush=True)
    print(
        f"  units_dir.is_dir(): {units_dir.is_dir()} | mydata_dir.is_dir(): {mydata_dir.is_dir()}",
        flush=True,
    )

    # Guard: fail fast instead of silently skipping units indexing.
    if not units_dir.is_dir():
        raise ValueError(f"units_dir is not a directory: {units_dir}")
    if not mydata_dir.is_dir():
        raise ValueError(f"mydata_dir is not a directory: {mydata_dir}")

    repo_root_raw = params.get("repo_root")
    repo_root_kw: Path | None
    if repo_root_raw is not None and str(repo_root_raw).strip():
        repo_root_kw = _resolve_under_repo(str(repo_root_raw).strip())
    else:
        repo_root_kw = _repo_root()

    # Locate a provided executor if available (prefer params, then state)
    executor = None
    if isinstance(params, dict):
        for k in ("executor", "_executor", "_thread_pool", "_shared_thread_pool"):
            v = params.get(k)
            if v is not None:
                executor = v
                break
    if executor is None and isinstance(state, dict):
        for k in ("_executor", "_thread_pool", "_shared_thread_pool", "executor"):
            v = state.get(k)
            if v is not None:
                executor = v
                break

    if executor is not None:
        submit_fn = getattr(executor, "submit", None)
        if not callable(submit_fn):
            executor = None

    # NEW: if no executor.submit is available, use provided event loop to schedule work
    loop_from_params = None
    if isinstance(params, dict):
        loop_from_params = params.get("_executor_loop") or params.get("_background_loop")
    if loop_from_params is None and isinstance(state, dict):
        loop_from_params = state.get("_executor_loop") or state.get("_background_loop")

    def _run_update_sync() -> dict[str, Any]:
        return run_update(
            rag_index_data_dir,
            units_dir,
            mydata_dir,
            embedding_model=embedding_model,
            repo_root=repo_root_kw,
        )

    try:
        if executor is not None:
            print("RagUpdate DEBUG: using provided executor", flush=True)
            fut = executor.submit(
                run_update,
                rag_index_data_dir,
                units_dir,
                mydata_dir,
                embedding_model=embedding_model,
                repo_root=repo_root_kw,
            )
            result = fut.result()

        elif loop_from_params is not None:
            print("RagUpdate DEBUG: using provided event loop", flush=True)
            # Ensure we are scheduling onto a running loop; then run sync update in a thread.
            async def _coro():
                return await asyncio.to_thread(_run_update_sync)

            fut = asyncio.run_coroutine_threadsafe(_coro(), loop_from_params)
            result = fut.result()

        else:
            print("RagUpdate DEBUG: running synchronously (no executor/loop)", flush=True)
            result = _run_update_sync()

        print("RagUpdate DEBUG run_update result:", flush=True)
        print(f"  ok={result.get('ok')} need_index={result.get('need_index')}", flush=True)
        print(f"  message={result.get('message')}", flush=True)
        print(
            f"  units_count={result.get('units_count')} mydata_count={result.get('mydata_count')}",
            flush=True,
        )
        print(f"  repo_canonical_count={result.get('repo_canonical_count')}", flush=True)
        print(f"  agents_rag_count={result.get('agents_rag_count')}", flush=True)
        print(f"  error={result.get('error')}", flush=True)

        # Clear rag index cache if present
        try:
            from units.rag.rag_search.rag_search import clear_rag_index_cache

            clear_rag_index_cache()
        except Exception:
            pass

    except Exception as e:
        err_msg = str(e)[:200]
        result = {
            "ok": False,
            "need_index": True,
            "units_count": 0,
            "mydata_count": 0,
            "repo_canonical_count": 0,
            "agents_rag_count": 0,
            "error": err_msg,
            "message": err_msg,
            "details": "",
        }
        return ({"data": result, "error": err_msg}, state)

    return ({"data": result, "error": None}, state)


def register_rag_update() -> None:
    """Register the RagUpdate unit type."""
    register_unit(
        UnitSpec(
            type_name="RagUpdate",
            input_ports=RAG_UPDATE_INPUT_PORTS,
            output_ports=RAG_UPDATE_OUTPUT_PORTS,
            step_fn=_rag_update_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="RAG index update: incremental ingest of units_dir, mydata_dir, canonical TaskVector *.json under the repo, and agents/**/*.md + *.py (UTF-8 docs) when rag_index_data_dir is under that repo; refreshes mydata/TaskVector/agents_team_members.md from agents/roles when role YAML or index state changes. Params: rag_index_data_dir, units_dir, mydata_dir, embedding_model, optional repo_root (settings.* refs). Output: data (result dict).",
        )
    )


__all__ = ["register_rag_update", "RAG_UPDATE_INPUT_PORTS", "RAG_UPDATE_OUTPUT_PORTS"]
