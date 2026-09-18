
from __future__ import annotations

import importlib

_TOOLS_ROOT_PACKAGE = "agents.tools"


def ensure_tools_registration(
    *,
    role_id: str | None = None,
) -> int:
    """
    Import and register tool action blocks.

    When ``role_id`` is provided, only tools listed in that role's
    configuration are registered. When it is omitted, all discovered tools
    are registered.

    ``role.tools`` contains tool IDs. Parser keys from ``tool.yaml`` are
    intentionally not used for registration.
    """
    if role_id is None:
        from agents.tools.catalog import all_tool_ids

        tool_ids = all_tool_ids()
    else:
        from agents.tools.catalog import ordered_tools_for_role_id

        # ordered_tools_for_role_id() returns (tool_id, parser_key) tuples.
        # Registration must use only the tool_id portion.
        tool_ids = tuple(
            dict.fromkeys(
                tool_id
                for tool_id, _parser_key in ordered_tools_for_role_id(role_id)
            )
        )

    registered = 0

    for tool_id in tool_ids:
        module_name = (
            f"{_TOOLS_ROOT_PACKAGE}.{tool_id}.action_block"
        )

        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            # Skip only when action_block itself does not exist.
            # Do not hide missing dependencies imported by action_block.
            if exc.name == module_name:
                continue
            raise

        registered += 1

    print(f"Registered {registered} tools for role_id={role_id!r}, tool_ids={tool_ids!r}")
    return registered
