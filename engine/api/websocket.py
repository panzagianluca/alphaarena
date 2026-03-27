"""WebSocket connection manager for Agent League.

Maintains a set of active WebSocket connections and broadcasts
JSON messages to all of them. Dead clients are silently removed.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    """Manages active WebSocket connections and broadcasts data."""

    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """Accept the WebSocket handshake and register the connection."""
        await ws.accept()
        self.connections.add(ws)
        logger.info("WebSocket connected (%d total)", len(self.connections))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection from the set (safe if not present)."""
        self.connections.discard(ws)
        logger.info("WebSocket disconnected (%d remaining)", len(self.connections))

    async def broadcast(self, data: dict) -> None:
        """Send JSON payload to every connected client.

        Per-connection exceptions are caught so one dead client
        doesn't break the broadcast for everyone else.  Dead clients
        are automatically removed from the connection set.
        """
        if not self.connections:
            return

        dead: set[WebSocket] = set()

        async def _send_safe(ws: WebSocket) -> None:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)

        await asyncio.gather(*[_send_safe(ws) for ws in self.connections])

        if dead:
            self.connections -= dead
            logger.info(
                "Removed %d dead WebSocket client(s) (%d remaining)",
                len(dead),
                len(self.connections),
            )
