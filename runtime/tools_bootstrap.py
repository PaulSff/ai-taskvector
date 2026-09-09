
from __future__ import annotations

import importlib

_TOOLS_ROOT_PACKAGE = "agents.tools"


def ensure_all_tools_registration() -> int:
    from agents.tools.catalog import all_tool_ids

    registered = 0

    for tool_id in all_tool_ids():
        module_name = f"{_TOOLS_ROOT_PACKAGE}.{tool_id}.action_block"

        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            # Skip only if action_block itself does not exist.
            # Do not hide missing dependencies imported by action_block.
            if exc.name == module_name:
                continue
            raise

        registered += 1

    print(f"Registered {registered} tools")
    return registered
