"""Tests for engine.core.market.MarketFeed."""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from engine.core.market import MarketFeed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COINGECKO_RESPONSE = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "current_price": 99000,
        "total_volume": 50_000_000_000,
        "price_change_percentage_1h_in_currency": 0.5,
        "price_change_percentage_24h_in_currency": 1.2,
    },
    {
        "id": "ethereum",
        "symbol": "eth",
        "current_price": 3900,
        "total_volume": 20_000_000_000,
        "price_change_percentage_1h_in_currency": -0.3,
        "price_change_percentage_24h_in_currency": 2.1,
    },
    {
        "id": "hedera-hashgraph",
        "symbol": "hbar",
        "current_price": 0.29,
        "total_volume": 500_000_000,
        "price_change_percentage_1h_in_currency": 1.0,
        "price_change_percentage_24h_in_currency": -0.5,
    },
    {
        "id": "dogecoin",
        "symbol": "doge",
        "current_price": 0.19,
        "total_volume": 3_000_000_000,
        "price_change_percentage_1h_in_currency": 0.1,
        "price_change_percentage_24h_in_currency": 0.8,
    },
]


def _mock_httpx_response(data=None, status_code=200, raise_exc=None):
    """Create a mock httpx response or raise an exception."""
    if raise_exc:
        mock = AsyncMock(side_effect=raise_exc)
        return mock

    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data if data is not None else COINGECKO_RESPONSE
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Init Tests
# ---------------------------------------------------------------------------

class TestMarketFeedInit:
    """Test MarketFeed initialization."""

    def test_creates_with_default_prices(self):
        feed = MarketFeed()
        # Should have starting price state for 4 assets
        assert "BTC" in feed._last_prices
        assert "ETH" in feed._last_prices
        assert "HBAR" in feed._last_prices
        assert "DOGE" in feed._last_prices

    def test_starting_prices_match_spec(self):
        feed = MarketFeed()
        assert feed._last_prices["BTC"] == 98000
        assert feed._last_prices["ETH"] == 3800
        assert feed._last_prices["HBAR"] == 0.28
        assert feed._last_prices["DOGE"] == 0.18

    def test_volume_history_starts_empty(self):
        feed = MarketFeed()
        assert feed._volume_history == {} or len(feed._volume_history) == 0


# ---------------------------------------------------------------------------
# fetch() Tests — successful CoinGecko call
# ---------------------------------------------------------------------------

class TestMarketFeedFetch:
    """Test fetch() with mocked CoinGecko responses."""

    @pytest.mark.asyncio
    async def test_fetch_returns_four_assets(self):
        feed = MarketFeed()
        with patch("engine.core.market.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(
                return_value=_mock_httpx_response(COINGECKO_RESPONSE)
            )
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await feed.fetch()

        assert len(result) == 4
        assert set(result.keys()) == {"BTC", "ETH", "HBAR", "DOGE"}

    @pytest.mark.asyncio
    async def test_fetch_maps_coingecko_ids_to_symbols(self):
        feed = MarketFeed()
        with patch("engine.core.market.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(
                return_value=_mock_httpx_response(COINGECKO_RESPONSE)
            )
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await feed.fetch()

        # hedera-hashgraph should map to HBAR
        assert "HBAR" in result
        assert result["HBAR"]["price_usd"] == 0.29

    @pytest.mark.asyncio
    async def test_fetch_returns_correct_price_fields(self):
        feed = MarketFeed()
        with patch("engine.core.market.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(
                return_value=_mock_httpx_response(COINGECKO_RESPONSE)
            )
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await feed.fetch()

        btc = result["BTC"]
        assert btc["price_usd"] == 99000
        assert btc["change_1h_pct"] == 0.5
        assert btc["change_24h_pct"] == 1.2
        assert btc["volume_trend"] in ("surging", "stable", "decreasing")

    @pytest.mark.asyncio
    async def test_fetch_updates_last_prices(self):
        feed = MarketFeed()
        with patch("engine.core.market.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(
                return_value=_mock_httpx_response(COINGECKO_RESPONSE)
            )
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            await feed.fetch()

        # After fetch, last_prices should be updated to CoinGecko values
        assert feed._last_prices["BTC"] == 99000
        assert feed._last_prices["ETH"] == 3900


# ---------------------------------------------------------------------------
# fetch() fallback tests
# ---------------------------------------------------------------------------

class TestMarketFeedFallback:
    """Test that fetch() falls back to mock prices on any exception."""

    @pytest.mark.asyncio
    async def test_fetch_falls_back_on_network_error(self):
        feed = MarketFeed()
        with patch("engine.core.market.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(side_effect=Exception("network error"))
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await feed.fetch()

        # Should still return 4 assets
        assert len(result) == 4
        assert set(result.keys()) == {"BTC", "ETH", "HBAR", "DOGE"}

    @pytest.mark.asyncio
    async def test_fetch_falls_back_on_timeout(self):
        import httpx as real_httpx

        feed = MarketFeed()
        with patch("engine.core.market.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(
                side_effect=real_httpx.TimeoutException("timeout")
            )
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await feed.fetch()

        assert len(result) == 4
        # Prices should be near starting prices (random walk)
        assert 0.90 * 98000 <= result["BTC"]["price_usd"] <= 1.10 * 98000


# ---------------------------------------------------------------------------
# _mock_prices() tests
# ---------------------------------------------------------------------------

class TestMockPrices:
    """Test _mock_prices() random walk behavior."""

    def test_mock_prices_returns_four_assets(self):
        feed = MarketFeed()
        result = feed._mock_prices()
        assert len(result) == 4
        assert set(result.keys()) == {"BTC", "ETH", "HBAR", "DOGE"}

    def test_mock_prices_have_required_fields(self):
        feed = MarketFeed()
        result = feed._mock_prices()
        for symbol, data in result.items():
            assert "price_usd" in data, f"{symbol} missing price_usd"
            assert "change_1h_pct" in data, f"{symbol} missing change_1h_pct"
            assert "change_24h_pct" in data, f"{symbol} missing change_24h_pct"
            assert "volume_trend" in data, f"{symbol} missing volume_trend"

    def test_mock_prices_random_walk_stays_near_initial(self):
        """After one call, prices should be within ~3% of starting."""
        feed = MarketFeed()
        result = feed._mock_prices()
        # BTC starts at 98000, one walk step is 0.97-1.03
        assert 98000 * 0.96 <= result["BTC"]["price_usd"] <= 98000 * 1.04

    def test_mock_prices_updates_state(self):
        """Calling mock_prices twice should produce different prices."""
        feed = MarketFeed()
        r1 = feed._mock_prices()
        r2 = feed._mock_prices()
        # Very unlikely all 4 are identical (random walk)
        any_different = any(
            r1[sym]["price_usd"] != r2[sym]["price_usd"]
            for sym in ["BTC", "ETH", "HBAR", "DOGE"]
        )
        assert any_different, "Two consecutive mock calls should differ"


# ---------------------------------------------------------------------------
# Volume trend tests
# ---------------------------------------------------------------------------

class TestVolumeTrend:
    """Test volume_trend computation from cached readings."""

    def test_first_reading_is_stable(self):
        """With no history, volume_trend should be 'stable'."""
        feed = MarketFeed()
        result = feed._mock_prices()
        for sym in ["BTC", "ETH", "HBAR", "DOGE"]:
            assert result[sym]["volume_trend"] == "stable"

    def test_surging_volume(self):
        """If current volume > last * 1.2, trend is 'surging'."""
        feed = MarketFeed()
        # Seed volume history with a low value
        feed._volume_history["BTC"] = [100]
        # Compute trend with a much higher volume
        trend = feed._compute_volume_trend("BTC", 200)
        assert trend == "surging"

    def test_decreasing_volume(self):
        """If current volume < last * 0.8, trend is 'decreasing'."""
        feed = MarketFeed()
        feed._volume_history["BTC"] = [200]
        trend = feed._compute_volume_trend("BTC", 100)
        assert trend == "decreasing"

    def test_stable_volume(self):
        """If volume is within 0.8-1.2 range of last, trend is 'stable'."""
        feed = MarketFeed()
        feed._volume_history["BTC"] = [100]
        trend = feed._compute_volume_trend("BTC", 105)
        assert trend == "stable"

    def test_volume_history_capped_at_two(self):
        """Volume history should keep at most 2 readings."""
        feed = MarketFeed()
        feed._volume_history["BTC"] = [100, 200]
        feed._compute_volume_trend("BTC", 300)
        assert len(feed._volume_history["BTC"]) == 2
        # Should contain the last 2 readings (200, 300)
        assert feed._volume_history["BTC"] == [200, 300]
