"""NodeRedCatalogueExtract unit: self-contained Node-RED catalogue extractor aligned with extractors.py behavior."""
from units.rag.node_red_catalogue_extractor.node_red_catalogue_extractor import (
    NODE_RED_CATALOGUE_EXTRACT_INPUT_PORTS,
    NODE_RED_CATALOGUE_EXTRACT_OUTPUT_PORTS,
    register_node_red_catalogue_extract,
)

__all__ = [
    "register_node_red_catalogue_extract",
    "NODE_RED_CATALOGUE_EXTRACT_INPUT_PORTS",
    "NODE_RED_CATALOGUE_EXTRACT_OUTPUT_PORTS",
]
