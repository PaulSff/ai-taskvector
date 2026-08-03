"""Aggregate unit (registered as type 'Aggregate'). See README.md for interface."""
from units.canonical.aggregate.aggregate import (
    AGGREGATE_INPUT_PORTS,
    AGGREGATE_OUTPUT_PORTS,
    register_aggregate,
)

__all__ = ["AGGREGATE_INPUT_PORTS", "AGGREGATE_OUTPUT_PORTS", "register_aggregate"]
