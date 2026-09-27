from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from core.schemas.primitives import Data, JsonObject

RagUpdateCallback = Callable[[str], Awaitable[None]]

def extract_successful_graph_after(
    msg: Data,
) -> JsonObject | None:
    def extract(value: object) -> JsonObject | None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return None

        if isinstance(value, dict):
            result = value.get("last_apply_result")

            if (
                isinstance(result, dict)
                and result.get("attempted") is True
                and result.get("success") is True
                and result.get("error") is None
                and isinstance(result.get("graph_after"), dict)
            ):
                return result["graph_after"]

            for child in value.values():
                graph_after = extract(child)
                if graph_after is not None:
                    return graph_after

        elif isinstance(value, list):
            for child in value:
                graph_after = extract(child)
                if graph_after is not None:
                    return graph_after

        return None

    return extract(msg)
