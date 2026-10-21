"""Load the raw 1m parquet and resample to the strategy timeframes.

Resampled frames are cached as parquet so repeated backtests are fast.
"""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("backtest.data")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "crypto_BTC_USD_1m.parquet"
CACHE = ROOT / "backtest" / "cache"
OHLCV_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def load_1m() -> pd.DataFrame:
    df = pd.read_parquet(RAW)
    df = df.rename(columns={c: c.lower() for c in df.columns})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def resample(df1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df1m.resample(rule, label="left", closed="left").agg(OHLCV_AGG).dropna()
    return out


def load_candles(tf: str = "15min", htf: str = "1h", use_cache: bool = True):
    """Return (df_tf, df_htf) OHLCV frames with a UTC DatetimeIndex."""
    CACHE.mkdir(exist_ok=True)
    f_tf, f_htf = CACHE / f"{tf}.parquet", CACHE / f"{htf}.parquet"
    if use_cache and f_tf.exists() and f_htf.exists():
        return pd.read_parquet(f_tf), pd.read_parquet(f_htf)
    df1m = load_1m()
    log.info("[data] loaded %d 1m rows %s -> %s", len(df1m), df1m.index[0], df1m.index[-1])
    df_tf, df_htf = resample(df1m, tf), resample(df1m, htf)
    df_tf.to_parquet(f_tf)
    df_htf.to_parquet(f_htf)
    log.info("[data] resampled: %d %s bars, %d %s bars", len(df_tf), tf, len(df_htf), htf)
    return df_tf, df_htf
