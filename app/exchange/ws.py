"""Delta Exchange WebSocket client (Role A).

Handles real-time ticker stream, order/position updates, heartbeat, and auto-reconnection.
"""
import asyncio
import json
import logging
import time
from typing import Optional, Callable, Dict, Any

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore

from app.config import settings

logger = logging.getLogger("app.exchange.ws")


class DeltaWebSocket:
    """Production WebSocket client for Delta Exchange testnet."""

    def __init__(
        self,
        ws_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        symbol: Optional[str] = None,
        on_ticker_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.ws_url = ws_url or settings.DELTA_WS_URL
        self.api_key = api_key or settings.DELTA_API_KEY
        self.api_secret = api_secret or settings.DELTA_API_SECRET
        self.symbol = symbol or settings.SYMBOL
        self.on_ticker_callback = on_ticker_callback

        self.latest_price: float = 0.0
        self.latest_ts: int = 0
        self.is_connected: bool = False
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        logger.info("[exchange.ws] Initialized DeltaWebSocket targeting %s", self.ws_url)

    async def connect_and_listen(self) -> None:
        """Connect to Delta WebSocket, subscribe to ticker, and listen for messages."""
        if websockets is None:
            logger.error("[exchange.ws] 'websockets' library is required. Install via pip install websockets")
            return

        self._running = True
        backoff = 1.0

        while self._running:
            try:
                logger.info("[exchange.ws] Connecting to %s...", self.ws_url)
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    self.is_connected = True
                    backoff = 1.0
                    logger.info("[exchange.ws] Connected! Subscribing to v2/ticker for %s", self.symbol)

                    # Subscribe to ticker channel
                    sub_message = {
                        "type": "subscribe",
                        "payload": {
                            "channels": [
                                {
                                    "name": "v2/ticker",
                                    "symbols": [self.symbol]
                                }
                            ]
                        }
                    }
                    await ws.send(json.dumps(sub_message))

                    # Message loop
                    while self._running:
                        try:
                            msg_str = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            msg = json.loads(msg_str)
                            self._handle_message(msg)
                        except asyncio.TimeoutError:
                            # Send heartbeat ping if quiet
                            await ws.send(json.dumps({"type": "ping"}))

            except (websockets.exceptions.ConnectionClosed, Exception) as exc:
                self.is_connected = False
                if not self._running:
                    break
                logger.warning("[exchange.ws] Disconnected (%s). Reconnecting in %.1fs...", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(30.0, backoff * 1.5)

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        """Parse incoming WebSocket messages."""
        msg_type = msg.get("type", "")
        if msg_type == "v2/ticker":
            mark_price = msg.get("mark_price") or msg.get("close")
            if mark_price is not None:
                self.latest_price = float(mark_price)
                self.latest_ts = int(time.time())
                if self.on_ticker_callback:
                    self.on_ticker_callback(msg)
        elif msg_type == "pong":
            pass
        elif msg_type == "subscriptions":
            logger.info("[exchange.ws] Subscription confirmed: %s", msg.get("channels"))

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> asyncio.Task:
        """Start WebSocket listener task in event loop."""
        active_loop = loop or asyncio.get_event_loop()
        self._task = active_loop.create_task(self.connect_and_listen())
        return self._task

    def stop(self) -> None:
        """Stop WebSocket connection."""
        self._running = False
        self.is_connected = False
        if self._task and not self._task.done():
            self._task.cancel()
