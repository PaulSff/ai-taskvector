"""
Canonical **Embedder** unit: sentence-transformers encoding (same defaults as former LlamaIndex HuggingFace path).

Params: ``model_name`` (HF / sentence-transformers id, e.g. ``sentence-transformers/all-MiniLM-L6-v2``).
Input: ``texts`` — ``str`` or ``list[str]``.
Output: ``embeddings`` — ``list[list[float]]`` (one vector per input string; normalized for cosine similarity).
"""
from __future__ import annotations

import os
from threading import Lock
from typing import Any

from units.registry import UnitSpec, register_unit

EMBEDDER_INPUT_PORTS = [("texts", "Any")]
EMBEDDER_OUTPUT_PORTS = [("embeddings", "Any")]

_MODEL_LOCK = Lock()
_MODEL_CACHE: dict[tuple[str, bool], Any] = {}


def _offline_flag() -> bool:
    try:
        from rag.ragconf_loader import rag_offline_raw

        return bool(rag_offline_raw())
    except Exception:
        return False


def normalize_sentence_transformer_model_id(model_name: str) -> str:
    """
    Map HuggingFace-style ids to the form ``SentenceTransformer`` prefers.

    ``sentence-transformers/all-MiniLM-L6-v2`` loads the same weights as ``all-MiniLM-L6-v2`` but avoids
    the "No sentence-transformers model found … Creating a new one with mean pooling" hub-resolution path.
    Other orgs (e.g. ``BAAI/...``) are left unchanged.
    """
    m = (model_name or "").strip()
    if m.startswith("sentence-transformers/"):
        rest = m.split("/", 1)[1].lstrip("/")
        return rest or m
    return m


def get_sentence_transformer(model_name: str) -> Any:
    """
    Return a cached ``SentenceTransformer`` for ``model_name`` (respects ``rag_offline`` / HF_HUB_OFFLINE).
    """
    mid = normalize_sentence_transformer_model_id(model_name)
    if not mid:
        raise ValueError("model_name is required")
    off = _offline_flag()
    if off:
        os.environ["HF_HUB_OFFLINE"] = "1"
    key = (mid, off)
    with _MODEL_LOCK:
        if key not in _MODEL_CACHE:
            from sentence_transformers import SentenceTransformer

            _MODEL_CACHE[key] = SentenceTransformer(mid)
        return _MODEL_CACHE[key]


def encode_texts(
    model_name: str,
    texts: list[str],
    *,
    batch_size: int = 64,
    normalize_embeddings: bool = True,
) -> list[list[float]]:
    """Encode non-empty stripped strings; skips empty strings (no row in output for those — caller should filter)."""
    model = get_sentence_transformer(model_name)
    out: list[list[float]] = []
    batch: list[str] = []
    for t in texts:
        s = (t or "").strip()
        if not s:
            continue
        batch.append(s)
        if len(batch) >= batch_size:
            emb = model.encode(
                batch,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=False,
            )
            out.extend(_rows_to_lists(emb))
            batch = []
    if batch:
        emb = model.encode(
            batch,
            normalize_embeddings=normalize_embeddings,
            show_progress_bar=False,
        )
        out.extend(_rows_to_lists(emb))
    return out


def _rows_to_lists(emb: Any) -> list[list[float]]:
    import numpy as np

    a = np.asarray(emb)
    if a.ndim == 1:
        return [list(map(float, a.tolist()))]
    return [list(map(float, a[i].tolist())) for i in range(len(a))]


def _embedder_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    model_name = str(params.get("model_name") or "").strip()
    if not model_name:
        return {"embeddings": []}, state
    raw = inputs.get("texts")
    if isinstance(raw, str):
        texts = [raw] if raw.strip() else []
    elif isinstance(raw, list):
        texts = [str(x) for x in raw]
    else:
        texts = []
    if not texts:
        return {"embeddings": []}, state
    vecs = encode_texts(model_name, texts)
    return {"embeddings": vecs}, state


def register_embedder() -> None:
    register_unit(
        UnitSpec(
            type_name="Embedder",
            input_ports=EMBEDDER_INPUT_PORTS,
            output_ports=EMBEDDER_OUTPUT_PORTS,
            step_fn=_embedder_step,
            role="embedding",
            description="Sentence-transformers embeddings: params.model_name, input texts (str or list[str]) → output embeddings (list of float vectors).",
        )
    )


__all__ = [
    "EMBEDDER_INPUT_PORTS",
    "EMBEDDER_OUTPUT_PORTS",
    "encode_texts",
    "get_sentence_transformer",
    "register_embedder",
]
