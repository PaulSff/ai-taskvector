from core.schemas.process_graph import Connection, Unit


def _resolve_port(conn: Connection, from_unit: Unit, to_unit: Unit) -> tuple[str, str]:
    """Resolve from_port/to_port to port names using graph Unit ports (Registry → Graph → Executor)."""
    fp = conn.from_port or "0"
    tp = conn.to_port or "0"
    if from_unit.output_ports:
        names = [p.name for p in from_unit.output_ports]
        try:
            idx = int(fp)
            if 0 <= idx < len(names):
                fp = names[idx]
        except (ValueError, TypeError):
            if fp in names:
                pass
            else:
                fp = names[0]
    if to_unit.input_ports:
        names = [p.name for p in to_unit.input_ports]
        try:
            idx = int(tp)
            if 0 <= idx < len(names):
                tp = names[idx]
        except (ValueError, TypeError):
            if tp in names:
                pass
            else:
                tp = names[0]
    return (fp, tp)
