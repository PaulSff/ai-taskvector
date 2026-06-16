import asyncio
import subprocess
from typing import Any


def _run_shell_block(source: str, timeout: float = 30.0) -> Any:
    """Run a unit's code_block as a bash script; return stdout/stderr as result (sync fallback)."""
    try:
        out = subprocess.run(
            ["bash", "-c", source],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (out.stdout or "").strip() or (out.stderr or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return ""


async def _run_shell_block_async(source: str, timeout: float = 30.0) -> Any:
    """Async variant using asyncio subprocess APIs."""
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        source,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        await proc.wait()
        return ""
    out = (stdout.decode() if stdout else "") or (stderr.decode() if stderr else "")
    return out.strip()
