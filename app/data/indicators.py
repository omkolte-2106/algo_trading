"""Technical indicators for candle series.

The functions return one value per input candle. Indicators that need a
warm-up period return ``math.nan`` until their first valid value.
"""

from collections.abc import Sequence

import numpy as np

from app.models import Candle


def _validate_period(period: int) -> None:
    """Reject invalid indicator periods."""
    if period < 1:
        raise ValueError("period must be at least 1")


def _values(candles: Sequence[Candle], field: str) -> np.ndarray:
    """Extract a candle field as a float array."""
    return np.fromiter((getattr(candle, field) for candle in candles), dtype=float)


def _true_range(candles: Sequence[Candle]) -> np.ndarray:
    """Calculate true range for each candle, including the first candle."""
    high = _values(candles, "high")
    low = _values(candles, "low")
    close = _values(candles, "close")
    if not len(candles):
        return np.array([], dtype=float)

    previous_close = np.roll(close, 1)
    previous_close[0] = close[0]
    return np.maximum.reduce((high - low, np.abs(high - previous_close), np.abs(low - previous_close)))


def _wilder_average(values: np.ndarray, period: int, first_index: int = 0) -> np.ndarray:
    """Apply Wilder's smoothed moving average with an SMA seed."""
    result = np.full(values.shape, np.nan, dtype=float)
    seed_end = first_index + period
    if seed_end > len(values):
        return result

    seed = values[first_index:seed_end]
    if not np.isfinite(seed).all():
        return result
    result[seed_end - 1] = seed.mean()
    for index in range(seed_end, len(values)):
        if np.isfinite(values[index]) and np.isfinite(result[index - 1]):
            result[index] = (result[index - 1] * (period - 1) + values[index]) / period
    return result


def compute_ema(candles: Sequence[Candle], period: int = 20) -> list[float]:
    """Calculate an EMA seeded with the first close, returning one value per candle."""
    _validate_period(period)
    close = _values(candles, "close")
    if not len(close):
        return []

    alpha = 2.0 / (period + 1.0)
    ema = np.empty_like(close)
    ema[0] = close[0]
    for index in range(1, len(close)):
        ema[index] = alpha * close[index] + (1.0 - alpha) * ema[index - 1]
    return ema.tolist()


def compute_atr(candles: Sequence[Candle], period: int = 14) -> list[float]:
    """Calculate Wilder's Average True Range; values before warm-up are NaN."""
    _validate_period(period)
    return _wilder_average(_true_range(candles), period).tolist()


def compute_adx(candles: Sequence[Candle], period: int = 14) -> list[float]:
    """Calculate Wilder's ADX; values before its two-stage warm-up are NaN."""
    _validate_period(period)
    count = len(candles)
    if not count:
        return []

    high = _values(candles, "high")
    low = _values(candles, "low")
    upward = np.diff(high, prepend=high[0])
    downward = -np.diff(low, prepend=low[0])
    plus_dm = np.where((upward > downward) & (upward > 0), upward, 0.0)
    minus_dm = np.where((downward > upward) & (downward > 0), downward, 0.0)
    tr = _true_range(candles)

    # Directional movement compares each candle with its predecessor, so the
    # first valid smoothing window starts at index 1.
    smooth_tr = _wilder_average(tr, period, first_index=1)
    smooth_plus = _wilder_average(plus_dm, period, first_index=1)
    smooth_minus = _wilder_average(minus_dm, period, first_index=1)
    plus_di = np.divide(100.0 * smooth_plus, smooth_tr, out=np.full(count, np.nan), where=smooth_tr != 0)
    minus_di = np.divide(100.0 * smooth_minus, smooth_tr, out=np.full(count, np.nan), where=smooth_tr != 0)
    denominator = plus_di + minus_di
    dx = np.divide(100.0 * np.abs(plus_di - minus_di), denominator,
                   out=np.full(count, np.nan), where=denominator != 0)
    return _wilder_average(dx, period, first_index=period).tolist()


def compute_rsi(candles: Sequence[Candle], period: int = 14) -> list[float]:
    """Calculate Wilder's RSI; values before the first full change window are NaN."""
    _validate_period(period)
    close = _values(candles, "close")
    count = len(close)
    if not count:
        return []

    changes = np.diff(close, prepend=close[0])
    gains = np.maximum(changes, 0.0)
    losses = np.maximum(-changes, 0.0)
    avg_gain = _wilder_average(gains, period, first_index=1)
    avg_loss = _wilder_average(losses, period, first_index=1)

    rsi = np.full(count, np.nan, dtype=float)
    no_loss = (avg_loss == 0) & np.isfinite(avg_gain)
    rsi[no_loss & (avg_gain > 0)] = 100.0
    rsi[no_loss & (avg_gain == 0)] = 50.0
    valid = np.isfinite(avg_gain) & np.isfinite(avg_loss) & (avg_loss > 0)
    relative_strength = np.divide(avg_gain, avg_loss, out=np.zeros(count), where=valid)
    rsi[valid] = 100.0 - 100.0 / (1.0 + relative_strength[valid])
    return rsi.tolist()
