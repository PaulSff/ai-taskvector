"""JsonFlattenExtract unit: generic recursive JSON-to-searchable-text extractor for RAG."""

from units.rag.json_flatten_extract.json_flatten_extract import (
    JSON_FLATTEN_EXTRACT_INPUT_PORTS,
    JSON_FLATTEN_EXTRACT_OUTPUT_PORTS,
    register_json_flatten_extract,
)

__all__ = [
    "register_json_flatten_extract",
    "JSON_FLATTEN_EXTRACT_INPUT_PORTS",
    "JSON_FLATTEN_EXTRACT_OUTPUT_PORTS",
]
