"""Aggregate unit (registered as type 'Aggregate'). See README.md for interface."""
from units.canonical.aggregate.aggregate import register_merge, MERGE_INPUT_PORTS, MERGE_OUTPUT_PORTS

__all__ = ["register_merge", "MERGE_INPUT_PORTS", "MERGE_OUTPUT_PORTS"]
