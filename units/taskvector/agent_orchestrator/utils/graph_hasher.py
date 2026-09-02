import hashlib
import json

from core.schemas.process_graph import ProcessGraph


def graph_md5(graph: ProcessGraph) -> str:
    return hashlib.md5(
        json.dumps(graph, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()
