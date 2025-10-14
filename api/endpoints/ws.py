# api/endpoints/ws.py
"""WebSocket endpoints for real-time analysis progress."""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from config import settings
from api.models.schemas import WebSocketEvent
from api.realtime import manager

router = APIRouter()

"""
Note: WebSocketManager class has been moved to api/realtime.py
to avoid circular imports. This module now imports the shared `manager`.
"""

async def _simulate_progress(analysis_id: str) -> None:
    stages = [
        ("ingest", "Reading contract"),
        ("chunk", "Splitting text"),
        ("embed", "Generating embeddings"),
        ("compare", "Matching against regulations"),
        ("violations", "Aggregating potential violations"),
    ]
    total = len(stages)
    for idx, (stage, detail) in enumerate(stages, start=1):
        await asyncio.sleep(1.2)
        evt = WebSocketEvent(
            type="progress",
            analysis_id=analysis_id,
            timestamp=datetime.utcnow(),
            schema_version=1,
            payload={"stage": stage, "detail": detail, "current": idx, "total": total}
        )
        await manager.broadcast(analysis_id, evt)
    complete = WebSocketEvent(
        type="complete",
        analysis_id=analysis_id,
        timestamp=datetime.utcnow(),
        schema_version=1,
        payload={"violations": 0, "duration_seconds": float(total) * 1.2}
    )
    await manager.broadcast(analysis_id, complete)

@router.websocket("/ws/analysis/{analysis_id}")
async def analysis_progress_ws(websocket: WebSocket, analysis_id: str, api_key: str | None = None):
    if not settings.ENABLE_WEBSOCKETS:
        await websocket.close(code=4000)
        return
    # Optional API key gate
    if settings.REQUIRE_API_KEY:
        # Support either query param or header (FastAPI doesn't parse headers automatically here)
        header_key = websocket.headers.get("x-api-key")
        key = api_key or header_key
        if not key or key != settings.API_KEY:
            await websocket.close(code=4401)
            return
    await manager.connect(analysis_id, websocket)
    # Send connected event
    init_evt = WebSocketEvent(
        type="connected",
        analysis_id=analysis_id,
        timestamp=datetime.utcnow(),
        schema_version=1,
        payload={"status": "listening"}
    )
    await manager.broadcast(analysis_id, init_evt)
    # Note: We rely on the analysis service to broadcast real-time events.
    # No built-in simulation to avoid circular imports and mixed streams.
    try:
        # Simple heartbeat: if client sends nothing, we'll keep the connection open via receive_text.
        # If you want server-initiated heartbeat, convert this to a gather with a periodic sender.
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(analysis_id, websocket)
    except Exception:
        await manager.disconnect(analysis_id, websocket)
        await websocket.close(code=1011)
