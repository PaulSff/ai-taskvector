# round_robin.py
import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class RoundRobinSlotConfig:
    n: int


class RoundRobinSlotAllocator:
    """
    Round-robin slot allocator with a max in-flight concurrency of `n`.

    Usage:
      allocator = RoundRobinSlotAllocator(n)
      slot = await allocator.acquire()
      try:
          ...
      finally:
          await allocator.release()
    """

    def __init__(self, n: int):
        if n <= 0:
            raise ValueError("n must be > 0")
        self._n = n
        self._sem = asyncio.Semaphore(n)
        self._next = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> int:
        await self._sem.acquire()
        async with self._lock:
            slot = self._next
            self._next = (self._next + 1) % self._n
            return slot

    async def release(self) -> None:
        self._sem.release()
