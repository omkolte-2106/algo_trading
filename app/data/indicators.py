"""Vectorized technical indicators using pandas/numpy (Role B).

Includes EMA, ATR, ADX, and RSI with unit tests against known values.
"""
from typing import List
from app.models import Candle

def compute_ema(candles: List[Candle], period: int = 20) -> List[float]:
    """Calculate Exponential Moving Average."""
    raise NotImplementedError("To be implemented in Phase B1")

def compute_atr(candles: List[Candle], period: int = 14) -> List[float]:
    """Calculate Average True Range."""
    raise NotImplementedError("To be implemented in Phase B1")

def compute_adx(candles: List[Candle], period: int = 14) -> List[float]:
    """Calculate Average Directional Index."""
    raise NotImplementedError("To be implemented in Phase B1")

def compute_rsi(candles: List[Candle], period: int = 14) -> List[float]:
    """Calculate Relative Strength Index."""
    raise NotImplementedError("To be implemented in Phase B1")
