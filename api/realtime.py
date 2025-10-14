"""Realtime WebSocket broadcasting utilities.

This module provides a shared WebSocketManager instance that can be imported
by both the WebSocket endpoint module and the analysis service without creating
import cycles.
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Dict, Set

from fastapi import WebSocket, HTTPException
from api.models.schemas import WebSocketEvent
from config import settings


class WebSocketManager:
    """Manages WebSocket connections grouped by analysis_id."""

    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._total_connections = 0
        self._last_sent_ts: Dict[str, float] = {}
        self._logger = logging.getLogger("complimate.api.ws")

    async def connect(self, analysis_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if settings.MAX_WS_CONNECTIONS and self._total_connections >= settings.MAX_WS_CONNECTIONS:
                await websocket.close(code=4003)
                raise HTTPException(status_code=503, detail="WebSocket connection limit reached")
            self._connections.setdefault(analysis_id, set()).add(websocket)
            self._total_connections += 1
            self._logger.info(
                "WS connected | analysis_id=%s total=%d group=%d",
                analysis_id,
                self._total_connections,
                len(self._connections.get(analysis_id, ()))
            )

    async def disconnect(self, analysis_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(analysis_id)
            if conns and websocket in conns:
                conns.remove(websocket)
                self._total_connections -= 1
                if not conns:
                    self._connections.pop(analysis_id, None)
            self._logger.info(
                "WS disconnected | analysis_id=%s total=%d group=%d",
                analysis_id,
                self._total_connections,
                len(self._connections.get(analysis_id, ()))
            )

    async def broadcast(self, analysis_id: str, event: WebSocketEvent) -> None:
        """Broadcast an event to all sockets subscribed to analysis_id.

        Safe to call from anywhere; failures to send will prune stale sockets.
        """
        data = event.model_dump()
        async with self._lock:
            targets = list(self._connections.get(analysis_id, []))
        stale = []
        for ws in targets:
            try:
                await ws.send_json(data)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                for ws in stale:
                    for aid, conns in list(self._connections.items()):
                        if ws in conns:
                            conns.remove(ws)
                            self._total_connections -= 1
                            if not conns:
                                self._connections.pop(aid, None)

    async def broadcast_throttled(self, analysis_id: str, event: WebSocketEvent, min_interval: float = 0.5) -> None:
        """Rate-limit progress spam by sending at most once per interval per analysis.

        Always bypass throttling for terminal events (complete, error).
        """
        if event.type in ("complete", "error"):
            return await self.broadcast(analysis_id, event)

        now = time.monotonic()
        last = self._last_sent_ts.get(analysis_id, 0.0)
        if (now - last) < min_interval:
            # Skip this update; a more recent one will arrive soon
            return
        self._last_sent_ts[analysis_id] = now
        await self.broadcast(analysis_id, event)


# Shared instance
manager = WebSocketManager()
