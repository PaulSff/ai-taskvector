"""Aggregate unit (registered as type 'Aggregate'). See README.md for interface."""
from units.canonical.aggregate.aggregate import register_aggregate, AGGREGATE_INPUT_PORTS, AGGREGATE_OUTPUT_PORTS

__all__ = ["register_aggregate", "AGGREGATE_INPUT_PORTS", "AGGREGATE_OUTPUT_PORTS"]
