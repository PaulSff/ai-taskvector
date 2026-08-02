"""Parses the tail of host to get the port value"""

import re


def _parse_host_port(endpoint: str) -> tuple[str, int]:
    # "tcp://127.0.0.1:6679" -> ("tcp://127.0.0.1", 6679)
    m = re.match(r"^(.*):(\d+)$", endpoint)
    if not m:
        raise ValueError(f"Unexpected endpoint format: {endpoint}")
    return m.group(1), int(m.group(2))
