"""Known-value tests for Role B technical indicators."""

import math

import pytest

from app.data.indicators import compute_adx, compute_atr, compute_ema, compute_rsi
from app.models import Candle


def make_candles(closes: list[float], highs: list[float] | None = None,
                 lows: list[float] | None = None) -> list[Candle]:
    """Build simple candles around the supplied close values."""
    highs = highs if highs is not None else [value + 1 for value in closes]
    lows = lows if lows is not None else [value - 1 for value in closes]
    return [
        Candle(ts=index, open=close, high=high, low=low, close=close, volume=1)
        for index, (close, high, low) in enumerate(zip(closes, highs, lows, strict=True))
    ]


def test_ema_matches_recursive_known_values() -> None:
    values = compute_ema(make_candles([10, 11, 12, 11]), period=3)
    assert values == pytest.approx([10, 10.5, 11.25, 11.125])


def test_atr_uses_true_range_and_wilder_smoothing() -> None:
    candles = make_candles([9, 11, 12], highs=[10, 12, 13], lows=[8, 9, 10])
    values = compute_atr(candles, period=2)
    assert math.isnan(values[0])
    assert values[1:] == pytest.approx([2.5, 2.75])


def test_adx_is_high_for_consistent_upward_movement() -> None:
    closes = [9, 10, 11, 12, 13, 14]
    candles = make_candles(
        closes,
        highs=[value + 1 for value in closes],
        lows=[value - 1 for value in closes],
    )
    values = compute_adx(candles, period=2)
    assert all(math.isnan(value) for value in values[:3])
    assert values[3:] == pytest.approx([100, 100, 100])


def test_rsi_matches_known_gain_loss_sequence() -> None:
    values = compute_rsi(make_candles([1, 2, 3, 2, 2]), period=2)
    assert all(math.isnan(value) for value in values[:2])
    assert values[2:] == pytest.approx([100, 50, 50])


@pytest.mark.parametrize("indicator", [compute_ema, compute_atr, compute_adx, compute_rsi])
def test_indicators_reject_nonpositive_period(indicator) -> None:
    with pytest.raises(ValueError, match="period"):
        indicator([], period=0)


def test_empty_candles_return_empty_results() -> None:
    assert compute_ema([]) == []
    assert compute_atr([]) == []
    assert compute_adx([]) == []
    assert compute_rsi([]) == []
