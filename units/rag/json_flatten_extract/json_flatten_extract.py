"""
JsonFlattenExtract unit: produce searchable RAG items from any JSON/YAML structure.

Recursively walks a JSON/YAML dict/list and extracts key-value pairs as searchable text.
- Text format: ``key: value | nested.key: value | ...``
- Metadata: top-level well-known fields (id, name, description, etc.) + file_path + origin + optional content_type override.
- If the top-level JSON is a list of dicts, one item is produced per element.

Params:
  - ``max_depth``       (int,       default 5):   max recursion depth.
  - ``max_value_len``   (int,       default 400): max characters per value before truncation.
  - ``max_pairs``       (int,       default 80):  max key-value pairs per item.
  - ``skip_keys``       (list[str], default []):  top-level keys to exclude from flattening.
  - ``origin``          (str,      default ""):   optional override for origin metadata.
  - ``content_type``    (str,      default ""):   optional override for metadata.content_type.
"""

from __future__ import annotations

import json

from core.schemas.primitives import Data, JsonObject, JsonValue, safe_int
from units.registry import UnitSpec, register_unit

JSON_FLATTEN_EXTRACT_INPUT_PORTS = [("data", "JsonValue"), ("file_path", "str")]
JSON_FLATTEN_EXTRACT_OUTPUT_PORTS = [("items", "list"), ("error", "str")]

# Fields that are worth promoting into the metadata dict if present at the top level
_WELL_KNOWN_META_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "name",
        "title",
        "description",
        "version",
        "author",
        "url",
        "source",
        "category",
        "categories",
        "type",
        "tags",
        "keywords",
        "origin",
        "label",
    }
)

_DEFAULT_MAX_DEPTH = 5
_DEFAULT_MAX_VALUE_LEN = 400
_DEFAULT_MAX_PAIRS = 80

type StepParams = dict[str, int | frozenset[str]]

# -----------------------------
# Recursive flattener
# -----------------------------


def _flatten_to_pairs(
    obj: JsonValue,
    prefix: str,
    max_depth: int,
    current_depth: int,
    max_value_len: int,
    skip_keys: frozenset[str],
) -> list[tuple[str, str]]:
    """Return a list of (dotted-key, value-string) pairs for all leaf values in *obj*."""
    pairs: list[tuple[str, str]] = []

    if current_depth >= max_depth:
        return pairs

    if isinstance(obj, dict):
        for k, v in obj.items():
            k_str = str(k)
            if k_str in skip_keys:
                continue
            key = f"{prefix}.{k_str}" if prefix else k_str

            if isinstance(v, dict):
                pairs.extend(
                    _flatten_to_pairs(
                        v, key, max_depth, current_depth + 1, max_value_len, skip_keys
                    )
                )
            elif isinstance(v, list):
                # Join primitive list members into one value string
                primitives = [
                    str(x).strip()
                    for x in v
                    if isinstance(x, (str, int, float, bool))
                    and x is not None
                    and str(x).strip()
                ]
                if primitives:
                    joined = " ".join(primitives)
                    if len(joined) > max_value_len:
                        joined = joined[:max_value_len] + "..."
                    pairs.append((key, joined))
                # Also recurse into any dicts nested inside the list
                for item in v:
                    if isinstance(item, dict):
                        pairs.extend(
                            _flatten_to_pairs(
                                item,
                                key,
                                max_depth,
                                current_depth + 1,
                                max_value_len,
                                skip_keys,
                            )
                        )
            elif v is not None:
                s = str(v).strip()
                if s:
                    if len(s) > max_value_len:
                        s = s[:max_value_len] + "..."
                    pairs.append((key, s))

    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                pairs.extend(
                    _flatten_to_pairs(
                        item,
                        prefix,
                        max_depth,
                        current_depth + 1,
                        max_value_len,
                        skip_keys,
                    )
                )
            elif item is not None:
                s = str(item).strip()
                if s:
                    if len(s) > max_value_len:
                        s = s[:max_value_len] + "..."
                    pairs.append((prefix, s))

    return pairs


# -----------------------------
# Metadata builder
# -----------------------------


def _build_metadata(obj: JsonObject, file_path: str, origin: str) -> JsonObject:
    """Promote well-known top-level fields into the metadata dict."""
    meta: JsonObject = {
        "file_path": file_path,
        "origin": origin or "generic_json",
    }
    for key in _WELL_KNOWN_META_KEYS:
        val = obj.get(key)
        if val is None:
            continue
        if isinstance(val, (dict, list)):
            try:
                meta[key] = json.dumps(val, ensure_ascii=False)
            except (TypeError, ValueError):
                meta[key] = str(val)
        else:
            s = str(val).strip()
            if s:
                meta[key] = s
    return meta


# -----------------------------
# Per-object item builder
# -----------------------------

def _make_item(
    obj: JsonObject,
    file_path: str,
    origin: str,
    *,
    max_depth: int,
    max_value_len: int,
    max_pairs: int,
    skip_keys: frozenset[str],
) -> JsonObject:
    pairs = _flatten_to_pairs(obj, "", max_depth, 0, max_value_len, skip_keys)[
        :max_pairs
    ]
    text = " | ".join(f"{k}: {v}" for k, v in pairs if v)
    meta = _build_metadata(obj, file_path, origin)
    return {"text": text, "metadata": meta}


def safe_clamped_int(value: object, default: int, low: int, high: int) -> int:
    n = safe_int(value)
    if n is None:
        n = default
    return max(low, min(n, high))

# -----------------------------
# Unit step
# -----------------------------

def _json_flatten_extract_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
):
    try:
        raw = inputs.get("data")

        if isinstance(raw, dict):
            parsed = raw.get("parsed") or raw.get("graph") or raw
            fp = str(raw.get("file_path") or "").strip()
            origin = str(raw.get("origin") or "generic_json").strip()
        else:
            parsed = raw
            fp = ""
            origin = "generic_json"

        fp_port = inputs.get("file_path")
        if isinstance(fp_port, str) and fp_port.strip():
            fp = fp_port.strip()

        max_depth = safe_clamped_int(params.get("max_depth"), _DEFAULT_MAX_DEPTH, 1, 10)
        max_value_len = safe_clamped_int(params.get("max_value_len"), _DEFAULT_MAX_VALUE_LEN, 50, 2000)
        max_pairs = safe_clamped_int(params.get("max_pairs"), _DEFAULT_MAX_PAIRS, 1, 500)

        raw_skip = params.get("skip_keys") or []
        skip_keys = frozenset(raw_skip) if isinstance(raw_skip, list) else frozenset()

        override_origin = str(params.get("origin") or "").strip()
        override_content_type = str(params.get("content_type") or "").strip()
        if override_origin:
            origin = override_origin

        items: list[JsonObject] = []

        def _set_content_type(item: JsonObject) -> None:
            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                item["metadata"] = metadata
            metadata["content_type"] = override_content_type

        if isinstance(parsed, list):
            for el in parsed:
                if isinstance(el, dict):
                    item = _make_item(
                        el,
                        fp,
                        origin,
                        max_depth=max_depth,
                        max_value_len=max_value_len,
                        max_pairs=max_pairs,
                        skip_keys=skip_keys,
                    )
                    if override_content_type:
                        _set_content_type(item)
                    items.append(item)
                else:
                    s = str(el).strip()
                    if s:
                        item_metadata: JsonObject = {
                            "file_path": fp,
                            "origin": origin,
                        }
                        if override_content_type:
                            item_metadata["content_type"] = override_content_type

                        items.append({
                            "text": s,
                            "metadata": item_metadata,
                        })

        elif isinstance(parsed, dict):
            item = _make_item(
                parsed,
                fp,
                origin,
                max_depth=max_depth,
                max_value_len=max_value_len,
                max_pairs=max_pairs,
                skip_keys=skip_keys,
            )
            if override_content_type:
                _set_content_type(item)
            items.append(item)

        else:
            if parsed is not None:
                s = str(parsed).strip()
                if s:
                    metadata: JsonObject = {
                        "file_path": fp,
                        "origin": origin,
                    }
                    if override_content_type:
                        metadata["content_type"] = override_content_type

                    items.append({
                        "text": s,
                        "metadata": metadata,
                    })

        return {"items": items, "error": ""}, state

    except (ValueError, TypeError) as e:
        return {"items": [], "error": str(e)}, state

# -----------------------------
# Registration
# -----------------------------


def register_json_flatten_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="JsonFlattenExtract",
            input_ports=JSON_FLATTEN_EXTRACT_INPUT_PORTS,
            output_ports=JSON_FLATTEN_EXTRACT_OUTPUT_PORTS,
            step_fn=_json_flatten_extract_step,
            environment_tags=["rag"],
            environment_tags_are_agnostic=False,
            description=(
                "Generic JSON extractor: recursively flattens any JSON dict/list into "
                "searchable 'key: value' text + well-known metadata fields. "
                "Handles RagDetectOrigin context envelopes. "
                "Params: max_depth (5), max_value_len (400), max_pairs (80), skip_keys ([]), "
                "origin (optional override), content_type (optional override)."
            ),
        )
    )


__all__ = [
    "JSON_FLATTEN_EXTRACT_INPUT_PORTS",
    "JSON_FLATTEN_EXTRACT_OUTPUT_PORTS",
    "register_json_flatten_extract",
]
