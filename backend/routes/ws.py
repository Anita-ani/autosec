"""
WebSocket live feed — streams alert events to dashboard clients in real time.

Connect:  ws://host/ws/feed?token=<JWT>

The JWT is validated on connection.  Analysts and operators are both accepted
(read-only stream — no mutation via this endpoint).  API keys are not accepted
here because browsers can't set arbitrary headers on WebSocket upgrades.

Message shape (server → client):
    {"type": "alert.created", "data": { ...alert fields... }}
    {"type": "alert.resolved", "data": {"alert_id": "..."}}
    {"type": "ping"}        — sent every 25 seconds to keep the connection alive

The client should respond to "ping" with any text frame to prevent timeouts.
On invalid/expired token the connection is closed with code 4001.
"""
import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from backend.services import auth as auth_svc
from backend.services.feed import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])

_PING_INTERVAL = 25  # seconds


@router.websocket("/ws/feed")
async def ws_feed(ws: WebSocket, token: str = Query(...)):
    try:
        auth_svc.decode_token(token)
    except JWTError:
        await ws.close(code=4001)
        return

    await manager.connect(ws)

    async def _ping_loop():
        while True:
            await asyncio.sleep(_PING_INTERVAL)
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break

    ping_task = asyncio.create_task(_ping_loop())
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        manager.disconnect(ws)
