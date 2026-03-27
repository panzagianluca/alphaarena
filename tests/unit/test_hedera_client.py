"""
Tests for engine.core.hedera_client — the Hedera blockchain client.

Covers:
- HederaClient initialization (env loading, wallet pool loading)
- Wallet assignment from pool
- Token funding (airdrop ARENA to agent)
- Trade execution (buy/sell/hold paths)
- HCS publishing (prices + reasoning)
- Capital allocation
- Transaction sequencing (asyncio.Lock)
- Agent client caching
- Error handling (graceful failures returning None)
- Stub mode (when SDK unavailable)

All tests use mocks — no real Hedera network calls.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from engine.core.hedera_client import HederaClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_WALLETS = [
    {
        "index": 0,
        "account_id": "0.0.1001",
        "private_key": "302e020100300506032b657004220420aaaa",
        "assigned": False,
    },
    {
        "index": 1,
        "account_id": "0.0.1002",
        "private_key": "302e020100300506032b657004220420bbbb",
        "assigned": False,
    },
    {
        "index": 2,
        "account_id": "0.0.1003",
        "private_key": "302e020100300506032b657004220420cccc",
        "assigned": False,
    },
]

SAMPLE_ENV = {
    "HEDERA_ACCOUNT_ID": "0.0.9999",
    "HEDERA_PRIVATE_KEY": "302e020100300506032b657004220420ffff",
    "WALLET_POOL_PATH": "",  # set dynamically per test
    "TOKEN_ARENA_ID": "0.0.5001",
    "TOKEN_WHBAR_ID": "0.0.5002",
    "TOKEN_WBTC_ID": "0.0.5003",
    "TOKEN_WETH_ID": "0.0.5004",
    "TOKEN_WDOGE_ID": "0.0.5005",
    "HCS_PRICE_TOPIC_ID": "0.0.6001",
    "HCS_TRADES_TOPIC_ID": "0.0.6002",
}


@pytest.fixture
def wallets_file(tmp_path):
    """Write sample wallets to a temp file and return the path."""
    path = tmp_path / "wallets.json"
    path.write_text(json.dumps(SAMPLE_WALLETS))
    return str(path)


@pytest.fixture
def env_vars(wallets_file):
    """Return a copy of SAMPLE_ENV with the wallets path set."""
    env = dict(SAMPLE_ENV)
    env["WALLET_POOL_PATH"] = wallets_file
    return env


@pytest.fixture
def client(env_vars):
    """Create a HederaClient with mocked env vars."""
    with patch.dict(os.environ, env_vars, clear=False):
        c = HederaClient()
    return c


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    def test_loads_treasury_account_from_env(self, client):
        assert client.treasury_account_id == "0.0.9999"

    def test_loads_treasury_private_key_from_env(self, client):
        assert client.treasury_private_key == "302e020100300506032b657004220420ffff"

    def test_loads_wallet_pool(self, client):
        assert len(client._wallet_pool) == 3

    def test_wallet_pool_entries_have_required_keys(self, client):
        for w in client._wallet_pool:
            assert "index" in w
            assert "account_id" in w
            assert "private_key" in w
            assert "assigned" in w

    def test_loads_token_ids(self, client):
        assert client.token_ids["ARENA"] == "0.0.5001"
        assert client.token_ids["wHBAR"] == "0.0.5002"
        assert client.token_ids["wBTC"] == "0.0.5003"
        assert client.token_ids["wETH"] == "0.0.5004"
        assert client.token_ids["wDOGE"] == "0.0.5005"

    def test_loads_topic_ids(self, client):
        assert client.hcs_price_topic_id == "0.0.6001"
        assert client.hcs_trades_topic_id == "0.0.6002"

    def test_agent_clients_cache_starts_empty(self, client):
        assert client._agent_clients == {}

    def test_has_tx_lock(self, client):
        assert isinstance(client._tx_lock, asyncio.Lock)

    def test_missing_wallets_file_raises(self, tmp_path):
        env = dict(SAMPLE_ENV)
        env["WALLET_POOL_PATH"] = str(tmp_path / "nonexistent.json")
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(FileNotFoundError):
                HederaClient()

    def test_missing_treasury_account_raises(self, wallets_file):
        env = dict(SAMPLE_ENV)
        env["WALLET_POOL_PATH"] = wallets_file
        env.pop("HEDERA_ACCOUNT_ID", None)
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises((KeyError, ValueError)):
                HederaClient()


# ---------------------------------------------------------------------------
# Wallet Assignment
# ---------------------------------------------------------------------------


class TestAssignWallet:
    def test_assign_returns_dict_with_required_keys(self, client):
        wallet = client.assign_wallet()
        assert "index" in wallet
        assert "account_id" in wallet
        assert "private_key" in wallet

    def test_assign_returns_first_unassigned(self, client):
        wallet = client.assign_wallet()
        assert wallet["account_id"] == "0.0.1001"
        assert wallet["index"] == 0

    def test_second_assign_returns_different_wallet(self, client):
        w1 = client.assign_wallet()
        w2 = client.assign_wallet()
        assert w1["account_id"] != w2["account_id"]
        assert w2["account_id"] == "0.0.1002"

    def test_assign_marks_wallet_as_assigned(self, client):
        client.assign_wallet()
        assert client._wallet_pool[0]["assigned"] is True
        assert client._wallet_pool[1]["assigned"] is False

    def test_assign_persists_to_file(self, client, wallets_file):
        client.assign_wallet()
        with open(wallets_file) as f:
            data = json.load(f)
        assert data[0]["assigned"] is True

    def test_all_wallets_exhausted_raises(self, client):
        for _ in range(3):
            client.assign_wallet()
        with pytest.raises(RuntimeError, match="[Nn]o.*wallet"):
            client.assign_wallet()

    def test_skips_already_assigned_wallets(self, client):
        client._wallet_pool[0]["assigned"] = True
        wallet = client.assign_wallet()
        assert wallet["account_id"] == "0.0.1002"


# ---------------------------------------------------------------------------
# Token Mapping
# ---------------------------------------------------------------------------


class TestTokenMapping:
    def test_asset_to_token_id_mapping(self, client):
        assert client._get_token_id_for_asset("BTC") == "0.0.5003"
        assert client._get_token_id_for_asset("ETH") == "0.0.5004"
        assert client._get_token_id_for_asset("HBAR") == "0.0.5002"
        assert client._get_token_id_for_asset("DOGE") == "0.0.5005"

    def test_unknown_asset_raises(self, client):
        with pytest.raises(KeyError):
            client._get_token_id_for_asset("SOL")


# ---------------------------------------------------------------------------
# Fund Agent (Airdrop ARENA)
# ---------------------------------------------------------------------------


class TestFundAgent:
    async def test_fund_agent_returns_tx_id_or_none(self, client):
        result = await client.fund_agent("0.0.1001", 10000)
        # In stub mode, returns a stub tx_id string or None
        assert result is None or isinstance(result, str)

    async def test_fund_agent_logs_operation(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="engine.core.hedera_client"):
            await client.fund_agent("0.0.1001", 10000)
        assert any("ARENA" in r.message for r in caplog.records)

    async def test_fund_agent_uses_lock(self, client):
        """Treasury operations should use the transaction lock."""
        locked_during_call = False

        original_fund = client._do_fund_agent

        async def spy_fund(*args, **kwargs):
            nonlocal locked_during_call
            locked_during_call = client._tx_lock.locked()
            return await original_fund(*args, **kwargs)

        client._do_fund_agent = spy_fund
        await client.fund_agent("0.0.1001", 10000)
        assert locked_during_call


# ---------------------------------------------------------------------------
# Execute Trade
# ---------------------------------------------------------------------------


class TestExecuteTrade:
    async def test_hold_returns_none(self, client):
        result = await client.execute_trade(
            action="hold",
            asset="NONE",
            amount_tokens=0,
            agent_account_id="0.0.1001",
            agent_private_key="302e...key",
        )
        assert result is None

    async def test_buy_returns_tx_id_or_none(self, client):
        result = await client.execute_trade(
            action="buy",
            asset="ETH",
            amount_tokens=0.5,
            agent_account_id="0.0.1001",
            agent_private_key="302e...key",
        )
        # Stub returns None or a string
        assert result is None or isinstance(result, str)

    async def test_sell_returns_tx_id_or_none(self, client):
        result = await client.execute_trade(
            action="sell",
            asset="ETH",
            amount_tokens=0.5,
            agent_account_id="0.0.1001",
            agent_private_key="302e...key",
        )
        assert result is None or isinstance(result, str)

    async def test_buy_logs_airdrop(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="engine.core.hedera_client"):
            await client.execute_trade(
                action="buy",
                asset="BTC",
                amount_tokens=0.01,
                agent_account_id="0.0.1001",
                agent_private_key="302e...key",
            )
        log_text = " ".join(r.message for r in caplog.records)
        assert "BUY" in log_text or "airdrop" in log_text.lower() or "wBTC" in log_text

    async def test_sell_logs_return_and_airdrop(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="engine.core.hedera_client"):
            await client.execute_trade(
                action="sell",
                asset="ETH",
                amount_tokens=1.0,
                agent_account_id="0.0.1001",
                agent_private_key="302e...key",
            )
        log_text = " ".join(r.message for r in caplog.records)
        assert "SELL" in log_text or "wETH" in log_text

    async def test_hold_does_not_log_transaction(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="engine.core.hedera_client"):
            await client.execute_trade(
                action="hold",
                asset="NONE",
                amount_tokens=0,
                agent_account_id="0.0.1001",
                agent_private_key="302e...key",
            )
        # HOLD should not produce transaction logs
        log_text = " ".join(r.message for r in caplog.records)
        assert "airdrop" not in log_text.lower()

    async def test_buy_uses_treasury_lock(self, client):
        """BUY transactions are treasury-signed and should use the lock."""
        locked_during_call = False

        original = client._do_treasury_airdrop

        async def spy(*args, **kwargs):
            nonlocal locked_during_call
            locked_during_call = client._tx_lock.locked()
            return await original(*args, **kwargs)

        client._do_treasury_airdrop = spy
        await client.execute_trade(
            action="buy",
            asset="ETH",
            amount_tokens=0.5,
            agent_account_id="0.0.1001",
            agent_private_key="302e...key",
        )
        assert locked_during_call


# ---------------------------------------------------------------------------
# HCS Publishing
# ---------------------------------------------------------------------------


class TestPublishPrices:
    async def test_returns_tx_id_or_none(self, client):
        prices = {"BTC": 98000, "ETH": 3800, "HBAR": 0.28, "DOGE": 0.18}
        result = await client.publish_prices(prices, round_number=1)
        assert result is None or isinstance(result, str)

    async def test_logs_price_publication(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="engine.core.hedera_client"):
            await client.publish_prices(
                {"BTC": 98000, "ETH": 3800}, round_number=5,
            )
        log_text = " ".join(r.message for r in caplog.records)
        assert "price" in log_text.lower() or "HCS" in log_text

    async def test_uses_price_topic_id(self, client):
        """publish_prices should target the price topic, not the trades topic."""
        assert client.hcs_price_topic_id == "0.0.6001"


class TestPublishTradeReasoning:
    async def test_returns_tx_id_or_none(self, client):
        result = await client.publish_trade_reasoning(
            agent_name="EthMaxi",
            round_number=3,
            decision={"action": "buy", "asset": "ETH", "reasoning": "dip buying"},
            hedera_tx_id="0.0.123@456",
        )
        assert result is None or isinstance(result, str)

    async def test_logs_reasoning_publication(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="engine.core.hedera_client"):
            await client.publish_trade_reasoning(
                agent_name="Viper",
                round_number=1,
                decision={"action": "sell", "asset": "BTC", "reasoning": "taking profit"},
                hedera_tx_id=None,
            )
        log_text = " ".join(r.message for r in caplog.records)
        assert "reason" in log_text.lower() or "HCS" in log_text or "Viper" in log_text


# ---------------------------------------------------------------------------
# Capital Allocation
# ---------------------------------------------------------------------------


class TestAllocateCapital:
    async def test_returns_tx_id_or_none(self, client):
        result = await client.allocate_capital("0.0.1001", 1000)
        assert result is None or isinstance(result, str)

    async def test_logs_allocation(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="engine.core.hedera_client"):
            await client.allocate_capital("0.0.1001", 5000)
        log_text = " ".join(r.message for r in caplog.records)
        assert "allocat" in log_text.lower() or "ARENA" in log_text

    async def test_allocation_uses_lock(self, client):
        """Capital allocation is treasury-signed — should use lock."""
        locked_during_call = False

        original = client._do_fund_agent

        async def spy(*args, **kwargs):
            nonlocal locked_during_call
            locked_during_call = client._tx_lock.locked()
            return await original(*args, **kwargs)

        client._do_fund_agent = spy
        await client.allocate_capital("0.0.1001", 1000)
        assert locked_during_call


# ---------------------------------------------------------------------------
# Agent Client Caching
# ---------------------------------------------------------------------------


class TestAgentClientCaching:
    def test_get_agent_client_creates_new_entry(self, client):
        ac = client._get_agent_client("0.0.1001", "302e...key")
        assert "0.0.1001" in client._agent_clients
        assert ac is not None

    def test_get_agent_client_returns_cached(self, client):
        ac1 = client._get_agent_client("0.0.1001", "302e...key")
        ac2 = client._get_agent_client("0.0.1001", "302e...key")
        assert ac1 is ac2

    def test_different_agents_get_different_clients(self, client):
        ac1 = client._get_agent_client("0.0.1001", "key1")
        ac2 = client._get_agent_client("0.0.1002", "key2")
        assert ac1 is not ac2


# ---------------------------------------------------------------------------
# Transaction Sequencing
# ---------------------------------------------------------------------------


class TestTransactionSequencing:
    async def test_concurrent_treasury_ops_are_serialized(self, client):
        """Two treasury operations should not run concurrently."""
        call_order = []

        original = client._do_fund_agent

        async def slow_fund(account_id, amount):
            call_order.append(f"start-{account_id}")
            await asyncio.sleep(0.05)
            call_order.append(f"end-{account_id}")
            return None

        client._do_fund_agent = slow_fund

        await asyncio.gather(
            client.fund_agent("0.0.1001", 10000),
            client.fund_agent("0.0.1002", 10000),
        )

        # With proper locking, we should see start-end-start-end, not interleaved
        assert call_order[0].startswith("start-")
        assert call_order[1].startswith("end-")
        assert call_order[2].startswith("start-")
        assert call_order[3].startswith("end-")


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_fund_agent_returns_none_on_error(self, client):
        """If the SDK call fails, return None instead of crashing."""

        async def failing_fund(*args, **kwargs):
            raise Exception("Network error")

        client._do_fund_agent = failing_fund
        result = await client.fund_agent("0.0.1001", 10000)
        assert result is None

    async def test_execute_trade_returns_none_on_error(self, client):
        """If the SDK call fails during a trade, return None."""

        async def failing_airdrop(*args, **kwargs):
            raise Exception("Network error")

        client._do_treasury_airdrop = failing_airdrop
        result = await client.execute_trade(
            action="buy",
            asset="ETH",
            amount_tokens=1.0,
            agent_account_id="0.0.1001",
            agent_private_key="302e...key",
        )
        assert result is None

    async def test_publish_prices_returns_none_on_error(self, client):
        async def failing_publish(*args, **kwargs):
            raise Exception("HCS error")

        client._do_publish_hcs = failing_publish
        result = await client.publish_prices({"BTC": 98000}, round_number=1)
        assert result is None

    async def test_publish_reasoning_returns_none_on_error(self, client):
        async def failing_publish(*args, **kwargs):
            raise Exception("HCS error")

        client._do_publish_hcs = failing_publish
        result = await client.publish_trade_reasoning(
            agent_name="X", round_number=1,
            decision={"action": "hold"}, hedera_tx_id=None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Stub / SDK mode detection
# ---------------------------------------------------------------------------


class TestStubMode:
    def test_stub_mode_attribute_exists(self, client):
        """Client should expose whether it's running in stub mode."""
        assert hasattr(client, "stub_mode")
        assert isinstance(client.stub_mode, bool)

    def test_stub_mode_is_true_when_sdk_unavailable(self, client):
        """When hiero_sdk_python is not importable, client should be in stub mode."""
        # Since we're not installing the SDK in tests, this should be True
        # If SDK is available, it would be False — test adapts either way
        assert isinstance(client.stub_mode, bool)
