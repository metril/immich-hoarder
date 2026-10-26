"""In-process pub/sub for job events (per-job streams plus a dashboard stream)."""

import asyncio
from collections import defaultdict, deque
from types import TracebackType
from typing import Any

QUEUE_SIZE = 1000


class Subscription:
    def __init__(self, bus: "EventBus", job_id: int | None) -> None:
        self._bus = bus
        self.job_id = job_id
        self._buf: deque[dict[str, Any]] = deque()
        self._wake = asyncio.Event()

    def empty(self) -> bool:
        return not self._buf

    def put(self, ev: dict[str, Any]) -> None:
        buf = self._buf
        if len(buf) >= QUEUE_SIZE:
            # drop exactly one oldest event; mark the hole with one coalesced gap
            if buf[0].get("type") == "gap":
                buf.popleft()
            buf.popleft()
            buf.appendleft({"type": "gap"})
        buf.append(ev)
        self._wake.set()

    def close(self) -> None:
        self._bus._remove(self)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(
        self,
        et: type[BaseException] | None,
        e: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __aiter__(self) -> "Subscription":
        return self

    async def __anext__(self) -> dict[str, Any]:
        while not self._buf:
            self._wake.clear()
            await self._wake.wait()
        return self._buf.popleft()


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[int | None, set[Subscription]] = defaultdict(set)

    def subscribe(self, job_id: int | None) -> Subscription:
        sub = Subscription(self, job_id)
        self._subs[job_id].add(sub)
        return sub

    def subscriber_count(self, job_id: int | None) -> int:
        return len(self._subs.get(job_id, ()))

    def _remove(self, sub: Subscription) -> None:
        subs = self._subs.get(sub.job_id)
        if subs is not None:
            subs.discard(sub)
            if not subs:
                del self._subs[sub.job_id]

    def publish(self, job_id: int | None, event: dict[str, Any]) -> None:
        for sub in tuple(self._subs.get(job_id, ())):
            sub.put(event)
        if job_id is not None:
            dash = self._subs.get(None)
            if dash:
                tagged = {**event, "job_id": job_id}
                for sub in tuple(dash):
                    sub.put(tagged)
