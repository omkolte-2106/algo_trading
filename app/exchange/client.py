"""Delta Exchange REST API client (Role A).

Handles HMAC-SHA256 request authentication, products resolution,
historical candles, balance, order placement, and cancellation with retry logic.
"""
import logging
from typing import Optional, List, Dict, Any
from app.models import Candle

logger = logging.getLogger("app.exchange.client")

class DeltaClient:
    """REST API client for Delta Exchange testnet."""
    def __init__(self, base_url: str, api_key: str = "", api_secret: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        logger.info(f"Initialized DeltaClient targeting {self.base_url}")

    def get_products(self) -> List[Dict[str, Any]]:
        """Fetch active products to resolve symbol -> product_id."""
        raise NotImplementedError("To be implemented in Phase A1")

    def get_candles(self, symbol: str, resolution: str, limit: int = 100) -> List[Candle]:
        """Fetch historical OHLCV candles."""
        raise NotImplementedError("To be implemented in Phase A1")
