"""Trend-following strategy with volatility filter on BTCUSD 15m candles (Role B).

Entry rules:
- Long: EMA(20) crosses above EMA(50), ADX(14) > 20, and 1h close > 1h EMA(50).
- Short: EMA(20) crosses below EMA(50), ADX(14) > 20, and 1h close < 1h EMA(50).
- Stop loss: 1.5 x ATR(14) from entry.
- Take profit: 2R.
"""
from typing import Optional, List
from app.models import Candle, Signal
from app.interfaces import Strategy

class TrendFollowingStrategy(Strategy):
    """Trend-following strategy implementation satisfying Strategy Protocol."""
    def __init__(self, symbol: str = "BTCUSD"):
        self.symbol = symbol

    def generate_signal(self, candles: List[Candle], htf_candles: List[Candle]) -> Optional[Signal]:
        """Generate trend signal from 15m and 1h candle feeds."""
        raise NotImplementedError("To be implemented in Phase B2")
