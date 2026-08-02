from __future__ import annotations

import asyncio
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=5)
        async with self._lock:
            self._subscribers[topic].add(queue)
        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[dict]) -> None:
        async with self._lock:
            self._subscribers[topic].discard(queue)

    async def publish(self, topic: str, payload: dict) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(topic, set()))
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(payload)
