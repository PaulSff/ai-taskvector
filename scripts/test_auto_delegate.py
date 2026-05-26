#!/usr/bin/env python3
"""Test runner for the auto-delegation workflow."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH (adjust parents[1] if scripts/ is deeper)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gui.components.settings import get_auto_delegate_workflow_path
from runtime.run import run_workflow


async def main():
    ad_path = get_auto_delegate_workflow_path()
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
    except Exception as e:
        print("run_workflow raised:", repr(e))
        return

    print("full ad_out:")
    print(json.dumps(ad_out, indent=2, ensure_ascii=False))

    # Try common extraction variants:
    dr = None
    if isinstance(ad_out, dict):
        dr = (
            (ad_out.get("delegate_req") or {}).get("data")
            or (ad_out.get("delegate_request") or {}).get("data")
            or (ad_out.get("delegate") or {}).get("data")
            or (ad_out.get("debug_delegate") or {}).get("data")
        )
        if not dr:
            for k, v in ad_out.items():
                if (
                    isinstance(v, dict)
                    and isinstance(v.get("data"), dict)
                    and "delegate_to" in (v.get("data") or {})
                ):
                    dr = v.get("data")
                    print("found delegate data under key:", k)
                    break

    print("extracted delegate data:")
    print(json.dumps(dr, indent=2, ensure_ascii=False))

    ok = (
        isinstance(dr, dict)
        and dr.get("ok") is True
        and (dr.get("delegate_to") or "").strip()
    )
    print("passes validation:", bool(ok))


if __name__ == "__main__":
    asyncio.run(main())
