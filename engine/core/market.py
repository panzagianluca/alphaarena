"""Real-time price feed via Binance WebSocket.

Connects to Binance combined ticker stream for BTC, ETH, HBAR, DOGE.
Prices update in memory ~every second. Falls back to CoinGecko REST
polling if WebSocket fails, and random-walk mock if both are down.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------

_BINANCE_TO_SYMBOL: dict[str, str] = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "DOGEUSDT": "DOGE",
    "HBARUSDT": "HBAR",
}

_BINANCE_STREAMS = ["btcusdt@ticker", "ethusdt@ticker", "dogeusdt@ticker", "hbarusdt@ticker"]
_BINANCE_WS_URL = f"wss://stream.binance.com:9443/stream?streams={'/'.join(_BINANCE_STREAMS)}"

# CoinGecko fallback
_CG_ID_TO_SYMBOL: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "hedera-hashgraph": "HBAR",
    "dogecoin": "DOGE",
}
_COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Starting prices for mock fallback
_STARTING_PRICES: dict[str, float] = {
    "BTC": 98_000,
    "ETH": 3_800,
    "HBAR": 0.28,
    "DOGE": 0.18,
}


class MarketFeed:
    """Real-time price feed with Binance WS, CoinGecko fallback, and mock fallback."""

    def __init__(self) -> None:
        self._prices: dict[str, dict[str, Any]] = {}
        self._last_mock_prices: dict[str, float] = dict(_STARTING_PRICES)
        self._ws_connected: bool = False
        self._ws_task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._ws_connected

    # ------------------------------------------------------------------
    # Public API: get latest prices (instant — reads from memory)
    # ------------------------------------------------------------------

    async def fetch(self) -> dict[str, dict[str, Any]] | None:
        """Return latest prices. Binance WS preferred, CoinGecko fallback.
        CoinGecko results are cached in self._prices so all agents see
        the SAME prices in the same cycle (prevents buy/sell price mismatch)."""
        if self._prices and self._ws_connected:
            return {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in self._prices.items()}

        # If we have cached prices from a previous CoinGecko call, use them
        # (they're stale but consistent — better than None)
        if self._prices:
            return {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in self._prices.items()}

        # First-time fallback: fetch from CoinGecko and CACHE in self._prices
        try:
            cg_prices = await self._fetch_coingecko()
            # Store in self._prices so subsequent calls return the same data
            for symbol, data in cg_prices.items():
                self._prices[symbol] = data
            logger.info("CoinGecko prices cached: %s", {s: d["price_usd"] for s, d in cg_prices.items()})
            return cg_prices
        except Exception:
            logger.warning("CoinGecko fallback also failed — no prices available")
            return None

    # ------------------------------------------------------------------
    # Binance WebSocket — runs as a background task
    # ------------------------------------------------------------------

    async def start_ws(self) -> None:
        """Start the Binance WebSocket stream as a background task."""
        if self._ws_task is not None:
            return
        self._ws_task = asyncio.create_task(self._ws_loop(), name="binance-ws")
        logger.info("Binance WebSocket stream starting...")

    async def _ws_loop(self) -> None:
        """Connect to Binance WS with auto-reconnect."""
        try:
            import websockets
        except ImportError:
            logger.warning("websockets not installed — using polling mode")
            return

        reconnect_delay = 1.0

        while True:
            try:
                async with websockets.connect(
                    _BINANCE_WS_URL,
                    ping_interval=20,
                    ping_timeout=60,
                    close_timeout=10,
                ) as ws:
                    self._ws_connected = True
                    reconnect_delay = 1.0
                    logger.info("Binance WebSocket connected — streaming 4 symbols")

                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                            data = msg.get("data", msg)
                            symbol_raw = data.get("s", "")
                            symbol = _BINANCE_TO_SYMBOL.get(symbol_raw)
                            if not symbol:
                                continue

                            price = float(data["c"])
                            change_pct = float(data.get("P", 0))
                            volume = float(data.get("v", 0))

                            # 1h change estimate (Binance only gives 24h)
                            change_1h_est = change_pct / 6.0

                            # Volume trend
                            volume_trend = "stable"
                            if symbol in self._prices:
                                prev_vol = self._prices[symbol].get("_raw_volume", volume)
                                if volume > prev_vol * 1.2:
                                    volume_trend = "surging"
                                elif volume < prev_vol * 0.8:
                                    volume_trend = "decreasing"

                            self._prices[symbol] = {
                                "price_usd": price,
                                "change_1h_pct": round(change_1h_est, 4),
                                "change_24h_pct": round(change_pct, 4),
                                "volume_trend": volume_trend,
                                "_raw_volume": volume,
                            }

                        except (KeyError, ValueError) as e:
                            logger.debug("Skipping malformed WS message: %s", e)

            except asyncio.CancelledError:
                logger.info("Binance WS task cancelled")
                break
            except Exception as e:
                self._ws_connected = False
                logger.warning("Binance WS disconnected: %s", e)

            self._ws_connected = False
            logger.info("Reconnecting in %.0fs...", reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60.0)

    # ------------------------------------------------------------------
    # CoinGecko REST fallback
    # ------------------------------------------------------------------

    async def _fetch_coingecko(self) -> dict[str, dict[str, Any]]:
        params = {
            "vs_currency": "usd",
            "ids": "hedera-hashgraph,bitcoin,ethereum,dogecoin",
            "price_change_percentage": "1h,24h",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(_COINGECKO_URL, params=params, timeout=5)
            resp.raise_for_status()
            coins = resp.json()

        result: dict[str, dict[str, Any]] = {}
        for coin in coins:
            symbol = _CG_ID_TO_SYMBOL.get(coin["id"])
            if not symbol:
                continue
            result[symbol] = {
                "price_usd": coin["current_price"],
                "change_1h_pct": coin.get("price_change_percentage_1h_in_currency", 0) or 0,
                "change_24h_pct": coin.get("price_change_percentage_24h_in_currency", 0) or 0,
                "volume_trend": "stable",
            }
        return result

    # ------------------------------------------------------------------
    # Mock fallback (random walk)
    # ------------------------------------------------------------------

    def _mock_prices(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for symbol, last_price in self._last_mock_prices.items():
            new_price = last_price * random.uniform(0.97, 1.03)
            self._last_mock_prices[symbol] = new_price
            change_pct = ((new_price - _STARTING_PRICES[symbol]) / _STARTING_PRICES[symbol]) * 100
            result[symbol] = {
                "price_usd": round(new_price, 6),
                "change_1h_pct": round(change_pct / 6, 4),
                "change_24h_pct": round(change_pct, 4),
                "volume_trend": random.choice(["stable", "surging", "decreasing"]),
            }
        return result


if __name__ == "__main__":
    async def _test():
        feed = MarketFeed()
        await feed.start_ws()
        await asyncio.sleep(5)
        prices = await feed.fetch()
        for symbol, data in prices.items():
            print(f"  {symbol}: ${data['price_usd']:,.4f} ({data['change_24h_pct']:+.2f}%)")
        print(f"  WS connected: {feed.connected}")

    asyncio.run(_test())
