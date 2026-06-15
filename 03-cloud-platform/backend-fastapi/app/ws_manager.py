"""WebSocket connection manager for WS /v1/stream/events."""
from __future__ import annotations

import asyncio
from typing import List

from fastapi import WebSocket

from .schemas import StreamEvent


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, event: StreamEvent) -> None:
        message = event.model_dump(mode="json")
        async with self._lock:
            targets = list(self._connections)
        stale: List[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                for ws in stale:
                    if ws in self._connections:
                        self._connections.remove(ws)


manager = ConnectionManager()
