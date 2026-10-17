"""Download public Delta testnet candles for backtesting."""

from __future__ import annotations

import argparse
import json
import logging
import time

from collections.abc import Iterator
from pathlib import Path

import httpx

from app.config import settings
from app.data.candles import validate_candles
from app.models import Candle


LOGGER = logging.getLogger("backtest.download_data")
MAX_CANDLES_PER_REQUEST = 2_000
RESOLUTIONS = {"15m": 15 * 60, "1h": 60 * 60}
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data"


def iter_time_ranges(start: int, end: int, interval: int) -> Iterator[tuple[int, int]]:
    """Yield inclusive, non-overlapping ranges of at most 2,000 candles."""
    if interval <= 0:
        raise ValueError("interval must be positive")
    if start > end:
        raise ValueError("start must not be after end")

    max_span = interval * (MAX_CANDLES_PER_REQUEST - 1)
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(end, chunk_start + max_span)
        yield chunk_start, chunk_end
        chunk_start = chunk_end + interval


def parse_candles(payload: dict[str, object]) -> list[Candle]:
    """Validate and convert a Delta candle response to shared Candle models."""
    if payload.get("success") is not True:
        raise ValueError("Delta candle response did not report success")
    rows = payload.get("result")
    if not isinstance(rows, list):
        raise ValueError("Delta candle response is missing its result list")

    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Delta candle result contains a non-object row")
        timestamp = row.get("time", row.get("ts"))
        if timestamp is None:
            raise ValueError("Delta candle row is missing its timestamp")
        candles.append(
            Candle(
                ts=int(timestamp),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )
    return candles


def fetch_candles(
    client: httpx.Client,
    base_url: str,
    symbol: str,
    resolution: str,
    days: int,
    now_ts: int,
) -> list[Candle]:
    """Fetch closed candles for a resolution over the requested day range."""
    if "testnet" not in base_url.lower():
        raise ValueError("historical data downloads must use a Delta testnet URL")
    if resolution not in RESOLUTIONS:
        raise ValueError(f"unsupported resolution: {resolution}")
    if not 90 <= days <= 180:
        raise ValueError("days must be between 90 and 180 (3 to 6 months)")

    interval = RESOLUTIONS[resolution]
    end = (now_ts // interval) * interval - interval
    start = end - days * 24 * 60 * 60 + interval
    candle_map: dict[int, Candle] = {}
    for chunk_start, chunk_end in iter_time_ranges(start, end, interval):
        response = client.get(
            f"{base_url.rstrip('/')}/v2/history/candles",
            params={
                "resolution": resolution,
                "symbol": symbol,
                "start": chunk_start,
                "end": chunk_end,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        for candle in parse_candles(response.json()):
            if start <= candle.ts <= end:
                candle_map[candle.ts] = candle

    candles = [candle_map[ts] for ts in sorted(candle_map)]
    if not candles:
        raise RuntimeError(f"Delta returned no {resolution} candles for {symbol}")
    if not validate_candles(candles):
        raise RuntimeError(f"Delta returned invalid or unordered {resolution} candles")
    return candles


def save_candles(candles: list[Candle], path: Path) -> None:
    """Write candle data atomically as a JSON array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    data = [candle.model_dump() for candle in candles]
    temporary_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def download_data(days: int, symbol: str, output_dir: Path) -> None:
    """Download 15-minute and 1-hour candles using the configured testnet."""
    base_url = settings.DELTA_BASE_URL
    if "testnet" not in base_url.lower():
        raise ValueError("DELTA_BASE_URL must point to a Delta testnet")

    now_ts = int(time.time())
    with httpx.Client(timeout=30.0) as client:
        for resolution in RESOLUTIONS:
            candles = fetch_candles(client, base_url, symbol, resolution, days, now_ts)
            path = output_dir / f"candles_{resolution}.json"
            save_candles(candles, path)
            LOGGER.info("saved %d %s candles to %s", len(candles), resolution, path)


def main() -> None:
    """Parse command-line options and download historical data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90, help="history length from 90 to 180 days")
    parser.add_argument("--symbol", default=settings.SYMBOL, help="Delta product symbol")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    download_data(args.days, args.symbol, args.output_dir)


if __name__ == "__main__":
    main()
