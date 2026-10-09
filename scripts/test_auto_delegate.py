"""Test runner for the auto-delegation workflow."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH (adjust parents[1] if scripts/ is deeper)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.roles.registry import DISPATCHER_ROLE_ID
from agents.roles.workflow_path import get_role_chat_workflow_path
from runtime.run import run_workflow


async def main():
    ad_path = get_role_chat_workflow_path(DISPATCHER_ROLE_ID)
    if not ad_path.is_file():
        print("workflow file not found:", ad_path)
        return
    user_message = "Could you add a template unit to the inject and a debug unit after the delegate_req?"
    try:
        ad_out = await asyncio.to_thread(
            run_workflow,
            ad_path,
            initial_inputs={"inject_msg": {"data": {"user_message": user_message}}},
        )
    except (FileNotFoundError, OSError, ValueError) as e:
        print("run_workflow raised:", repr(e))
        return

    print("full ad_out:")
    print(json.dumps(ad_out, indent=2, ensure_ascii=False))

    # Try common extraction variants:
    dr = None
    if isinstance(ad_out, dict):
        for key in ("delegate_req", "delegate_request", "delegate", "debug_delegate"):
            candidate = ad_out.get(key)
            if isinstance(candidate, dict):
                data = candidate.get("data")
                if isinstance(data, dict) and data:
                    dr = data
                    break
        if not dr:
            for k, v in ad_out.items():
                if not isinstance(v, dict):
                    continue

                data = v.get("data")
                if isinstance(data, dict) and "delegate_to" in data:
                    dr = data
                    print("found delegate data under key:", k)
                    break

    print("extracted delegate data:")
    print(json.dumps(dr, indent=2, ensure_ascii=False))

    delegate_to = dr.get("delegate_to") if isinstance(dr, dict) else None

    ok = (
        isinstance(dr, dict)
        and dr.get("ok") is True
        and isinstance(delegate_to, str)
        and bool(delegate_to.strip())
    )
    print("passes validation:", bool(ok))



if __name__ == "__main__":
    asyncio.run(main())
