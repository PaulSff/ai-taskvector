from core.schemas.agent_node import (
    EXECUTOR_EXCLUDED_TYPES,
)
from core.schemas.process_graph import ProcessGraph
from units.registry import get_unit_spec


def _validate_graph_for_execution(graph: ProcessGraph) -> None:
    """Raise ValueError if the graph is invalid for execution (invalid connections or ports)."""
    unit_ids = {u.id: u for u in graph.units}
    process_ids = {
        u.id
        for u in graph.units
        if u.type not in EXECUTOR_EXCLUDED_TYPES and get_unit_spec(u.type) is not None
    }
    for c in graph.connections:
        # If connection references units not in graph, treat as valid
        if c.from_id not in unit_ids or c.to_id not in unit_ids:
            continue
        from_unit = unit_ids[c.from_id]
        to_unit = unit_ids[c.to_id]
        if c.from_id in process_ids and not from_unit.output_ports:
            raise ValueError(
                f"Connection from unit '{c.from_id}' has no output_ports; "
                "every process unit used as a connection source must have output_ports on the graph."
            )
        if c.to_id in process_ids and not to_unit.input_ports:
            raise ValueError(
                f"Connection to unit '{c.to_id}' has no input_ports; "
                "every process unit used as a connection target must have input_ports on the graph."
            )
        if c.from_id in process_ids and from_unit.output_ports:
            fp_raw = c.from_port or "0"
            try:
                fp = int(fp_raw)
            except (ValueError, TypeError):
                names = [p.name for p in from_unit.output_ports]
                if fp_raw in names:
                    fp = names.index(fp_raw)
                else:
                    raise ValueError(
                        f"Connection from_port must be a valid index or port name for unit '{c.from_id}', got '{c.from_port}'."
                    ) from None
            if fp < 0 or fp >= len(from_unit.output_ports):
                raise ValueError(
                    f"Connection from_port '{c.from_port}' out of range for unit '{c.from_id}' "
                    f"(has {len(from_unit.output_ports)} output_ports)."
                )
        if c.to_id in process_ids and to_unit.input_ports:
            tp_raw = c.to_port or "0"
            try:
                tp = int(tp_raw)
            except (ValueError, TypeError):
                names = [p.name for p in to_unit.input_ports]
                if tp_raw in names:
                    tp = names.index(tp_raw)
                else:
                    raise ValueError(
                        f"Connection to_port must be a valid index or port name for unit '{c.to_id}', got '{c.to_port}'."
                    ) from None
            if tp < 0 or tp >= len(to_unit.input_ports):
                raise ValueError(
                    f"Connection to_port '{c.to_port}' out of range for unit '{c.to_id}' "
                    f"(has {len(to_unit.input_ports)} input_ports)."
                )
