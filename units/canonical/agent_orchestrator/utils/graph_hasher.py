import hashlib
import json
from typing import Any


def _graph_md5(graph: Any) -> str:
    return hashlib.md5(
        json.dumps(graph, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()
