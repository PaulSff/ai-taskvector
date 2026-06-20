from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SingleInstanceLock:
    def __init__(self, lockfile_path: Path):
        self.lockfile_path = lockfile_path
        self._lock_fd: Optional[int] = None

    def acquire(self) -> None:
        self.lockfile_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            fd = os.open(
                str(self.lockfile_path),
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
            )
        except FileExistsError:
            # Best-effort stale detection
            try:
                with open(self.lockfile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pid = int(data.get("pid", -1))
                if pid > 0:
                    try:
                        os.kill(pid, 0)
                        raise RuntimeError(
                            f"Another instance appears to be running (pid={pid})."
                        )
                    except ProcessLookupError:
                        pass  # stale
            except RuntimeError:
                raise
            except Exception:
                # If we can't validate, treat as active
                raise RuntimeError("Lockfile exists; another instance may be running.")

            os.remove(self.lockfile_path)
            fd = os.open(
                str(self.lockfile_path),
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
            )

        self._lock_fd = fd
        payload = {
            "pid": os.getpid(),
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        os.write(fd, json.dumps(payload).encode("utf-8"))
        os.fsync(fd)

    def release(self) -> None:
        try:
            if self._lock_fd is not None:
                os.close(self._lock_fd)
        finally:
            self._lock_fd = None
            try:
                self.lockfile_path.unlink()
            except FileNotFoundError:
                pass
