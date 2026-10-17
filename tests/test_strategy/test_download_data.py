"""Tests for the public candle-history downloader."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backtest.download_data import fetch_candles, iter_time_ranges, parse_candles


def test_time_ranges_split_at_delta_response_limit() -> None:
    interval = 60
    end = interval * 2_000
    assert list(iter_time_ranges(0, end, interval)) == [
        (0, interval * 1_999),
        (interval * 2_000, interval * 2_000),
    ]


def test_time_ranges_reject_invalid_input() -> None:
    with pytest.raises(ValueError, match="interval"):
        list(iter_time_ranges(0, 1, 0))
    with pytest.raises(ValueError, match="start"):
        list(iter_time_ranges(2, 1, 1))


def test_parse_candles_uses_delta_time_field() -> None:
    candles = parse_candles({
        "success": True,
        "result": [{"time": 123, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 4}],
    })
    assert candles[0].model_dump() == {
        "ts": 123,
        "open": 10.0,
        "high": 12.0,
        "low": 9.0,
        "close": 11.0,
        "volume": 4.0,
    }


def test_fetch_candles_chunks_requests_and_omits_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        query = parse_qs(urlparse(str(request.url)).query)
        interval = 60 * 60
        start = int(query["start"][0])
        end = int(query["end"][0])
        candles = [
            {"time": ts, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}
            for ts in range(start, end + 1, interval)
        ]
        return httpx.Response(200, json={"success": True, "result": candles})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        candles = fetch_candles(
            client,
            "https://cdn-ind.testnet.deltaex.org",
            "BTCUSD",
            "1h",
            days=90,
            now_ts=1_800_000_000,
        )

    assert len(candles) == 90 * 24
    assert len(requests) == 2
    assert all(request.headers.get("Authorization") is None for request in requests)
    assert [candle.ts for candle in candles] == sorted(candle.ts for candle in candles)


def test_fetch_candles_rejects_non_testnet_url() -> None:
    with httpx.Client() as client, pytest.raises(ValueError, match="testnet"):
        fetch_candles(client, "https://api.delta.exchange", "BTCUSD", "1h", 90, 1_800_000_000)
