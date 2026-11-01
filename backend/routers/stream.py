"""
SmartLog AI — live stream route.

WS /ws/stream: stays connected but emits NOTHING by default. There is no
synthetic log generator. After an ingest (file upload or URL scrape) the
newly ingested incident rows — capped at the 50 most recent — are pushed to
every connected client as {"type": "incident", "data": <incident>} frames.
"""

import asyncio
from typing import Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Connected clients + the server's event loop, set at startup so the
# synchronous ingest task can schedule sends thread-safely.
_clients: Set[WebSocket] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None

PUSH_LIMIT = 50  # max newly ingested rows broadcast per ingest


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Remember the main event loop (called once from app.lifespan)."""
    global _loop
    _loop = loop


@router.websocket("/ws/stream")
async def stream(ws: WebSocket) -> None:
    """Hold the socket open. Only real, ingest-driven frames are sent."""
    await ws.accept()
    _clients.add(ws)
    try:
        # The hello frame confirms the connection without fabricating data.
        await ws.send_json({"type": "hello", "message": "stream connected"})
        while True:
            # Nothing synthetic is generated here. Incoming (client-to-server)
            # frames keep the ping/pong machinery happy; any disconnect raises.
            await ws.receive_text()
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 — a broken socket must not crash the server
        pass
    finally:
        _clients.discard(ws)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


async def _broadcast(payload: dict) -> None:
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001 — dead clients are dropped silently
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


def push_incident_frames(incident_dicts: list[dict]) -> None:
    """Thread-safe push of newly ingested rows (≤50 newest) to live clients."""
    if not incident_dicts or _loop is None or not _clients:
        return
    for data in incident_dicts[-PUSH_LIMIT:]:
        try:
            asyncio.run_coroutine_threadsafe(
                _broadcast({"type": "incident", "data": data}), _loop
            )
        except RuntimeError:  # loop already closed
            return
