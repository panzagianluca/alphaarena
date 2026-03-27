"""
Tests for user wallet support.

Covers:
- Schema: users table exists with correct columns
- Schema: allocations table has user_id column
- HederaClient.transfer_user_to_agent method
- POST /api/user/wallet endpoint
- GET /api/user/{user_id}/balance endpoint
- POST /api/allocate with user_id (user-funded allocation)
- POST /api/agents/create with user_id (agent creation cost)
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from engine.db.database import Database


# ---------------------------------------------------------------------------
# DB Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db(tmp_path):
    """Provide an initialized Database pointing at a temp file."""
    db_path = str(tmp_path / "test.db")
    database = Database(db_path=db_path)
    await database.init()
    yield database
    await database.close()


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------

class TestSchema:
    """Verify schema changes for user wallet support."""

    @pytest.mark.asyncio
    async def test_users_table_exists(self, db):
        row = await db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        assert row is not None, "Table 'users' was not created"

    @pytest.mark.asyncio
    async def test_users_table_columns(self, db):
        """Users table should have id, hedera_account_id, wallet_index, arena_balance, created_at."""
        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index, arena_balance) "
            "VALUES (?, ?, ?, ?)",
            ("user-001", "0.0.1001", 0, 50000.0),
        )
        user = await db.fetchone("SELECT * FROM users WHERE id = ?", ("user-001",))
        assert user is not None
        assert user["id"] == "user-001"
        assert user["hedera_account_id"] == "0.0.1001"
        assert user["wallet_index"] == 0
        assert user["arena_balance"] == 50000.0
        assert "created_at" in user

    @pytest.mark.asyncio
    async def test_users_default_balance(self, db):
        """Default arena_balance should be 50000.0."""
        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index) VALUES (?, ?, ?)",
            ("user-002", "0.0.1002", 1),
        )
        user = await db.fetchone("SELECT * FROM users WHERE id = ?", ("user-002",))
        assert user is not None
        assert user["arena_balance"] == 50000.0

    @pytest.mark.asyncio
    async def test_allocations_has_user_id_column(self, db):
        """allocations table should have a user_id column."""
        # Insert a season first (foreign key)
        await db.execute(
            "INSERT INTO seasons (id, status) VALUES (?, ?)", (1, "active")
        )
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
            ("a1", "Bot", "thesis", "prompt"),
        )
        await db.execute(
            "INSERT INTO allocations (agent_id, season_id, amount, user_id) "
            "VALUES (?, ?, ?, ?)",
            ("a1", 1, 1000.0, "user-001"),
        )
        row = await db.fetchone(
            "SELECT user_id FROM allocations WHERE agent_id = ?", ("a1",)
        )
        assert row is not None
        assert row["user_id"] == "user-001"

    @pytest.mark.asyncio
    async def test_allocations_user_id_nullable(self, db):
        """user_id in allocations should be nullable for backward compatibility."""
        await db.execute(
            "INSERT INTO seasons (id, status) VALUES (?, ?)", (1, "active")
        )
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
            ("a1", "Bot", "thesis", "prompt"),
        )
        await db.execute(
            "INSERT INTO allocations (agent_id, season_id, amount) VALUES (?, ?, ?)",
            ("a1", 1, 1000.0),
        )
        row = await db.fetchone(
            "SELECT user_id FROM allocations WHERE agent_id = ?", ("a1",)
        )
        assert row is not None
        assert row["user_id"] is None


# ---------------------------------------------------------------------------
# HederaClient Tests
# ---------------------------------------------------------------------------

SAMPLE_WALLETS = [
    {"index": 0, "account_id": "0.0.1001", "private_key": "key0", "assigned": False},
    {"index": 1, "account_id": "0.0.1002", "private_key": "key1", "assigned": False},
    {"index": 2, "account_id": "0.0.1003", "private_key": "key2", "assigned": False},
]

SAMPLE_ENV = {
    "HEDERA_ACCOUNT_ID": "0.0.9999",
    "HEDERA_PRIVATE_KEY": "302e020100300506032b657004220420ffff",
    "WALLET_POOL_PATH": "",
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
    path = tmp_path / "wallets.json"
    path.write_text(json.dumps(SAMPLE_WALLETS))
    return str(path)


@pytest.fixture
def env_vars(wallets_file):
    env = dict(SAMPLE_ENV)
    env["WALLET_POOL_PATH"] = wallets_file
    return env


@pytest.fixture
def client(env_vars):
    from engine.core.hedera_client import HederaClient
    with patch.dict(os.environ, env_vars, clear=False):
        c = HederaClient()
    return c


class TestTransferUserToAgent:
    """Tests for HederaClient.transfer_user_to_agent."""

    @pytest.mark.asyncio
    async def test_method_exists(self, client):
        """transfer_user_to_agent should be a method on HederaClient."""
        assert hasattr(client, "transfer_user_to_agent")
        assert callable(client.transfer_user_to_agent)

    @pytest.mark.asyncio
    async def test_successful_transfer(self, client):
        """Should call _do_agent_send and return tx_id."""
        client._do_agent_send = AsyncMock(return_value="tx-abc-123")
        tx_id = await client.transfer_user_to_agent(
            user_account_id="0.0.1001",
            user_private_key="key0",
            agent_account_id="0.0.2001",
            amount=5000,
        )
        assert tx_id == "tx-abc-123"
        client._do_agent_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_transfer_passes_arena_token(self, client):
        """Should use the ARENA token ID for transfers."""
        client._do_agent_send = AsyncMock(return_value="tx-456")
        await client.transfer_user_to_agent(
            user_account_id="0.0.1001",
            user_private_key="key0",
            agent_account_id="0.0.2001",
            amount=1000,
        )
        call_args = client._do_agent_send.call_args
        # token_id should be ARENA
        assert "0.0.5001" in str(call_args)

    @pytest.mark.asyncio
    async def test_transfer_failure_returns_none(self, client):
        """Should return None and log error on failure."""
        client._do_agent_send = AsyncMock(side_effect=Exception("network error"))
        tx_id = await client.transfer_user_to_agent(
            user_account_id="0.0.1001",
            user_private_key="key0",
            agent_account_id="0.0.2001",
            amount=1000,
        )
        assert tx_id is None


# ---------------------------------------------------------------------------
# API Route Tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_app(db, client):
    """Create a mock app state for route testing."""
    app_state = MagicMock()
    app_state.db = db
    app_state.hedera_client = client
    app_state.orchestrator = None

    app = MagicMock()
    app.state = app_state
    return app


def _make_request(app, body=None):
    """Create a mock Request with app state and optional JSON body."""
    request = MagicMock()
    request.app = app

    async def json_fn():
        return body or {}

    request.json = json_fn
    return request


class TestCreateUserWallet:
    """Tests for POST /api/user/wallet."""

    @pytest.mark.asyncio
    async def test_creates_user_wallet(self, mock_app, db):
        """Should create a user with a wallet and fund with 50k ARENA."""
        from engine.api.routes import create_user_wallet

        hedera = mock_app.state.hedera_client
        hedera.fund_agent = AsyncMock(return_value="tx-fund-001")

        request = _make_request(mock_app)
        result = await create_user_wallet(request)

        assert "user_id" in result
        assert result["user_id"].startswith("user-")
        assert "hedera_account_id" in result
        assert result["arena_balance"] == 50000.0
        assert result["hedera_tx_id"] == "tx-fund-001"

    @pytest.mark.asyncio
    async def test_creates_user_in_db(self, mock_app, db):
        """Should insert user row into database."""
        from engine.api.routes import create_user_wallet

        hedera = mock_app.state.hedera_client
        hedera.fund_agent = AsyncMock(return_value="tx-fund-002")

        request = _make_request(mock_app)
        result = await create_user_wallet(request)

        user = await db.fetchone(
            "SELECT * FROM users WHERE id = ?", (result["user_id"],)
        )
        assert user is not None
        assert user["arena_balance"] == 50000.0
        assert user["hedera_account_id"] == result["hedera_account_id"]


class TestGetUserBalance:
    """Tests for GET /api/user/{user_id}/balance."""

    @pytest.mark.asyncio
    async def test_returns_user_balance(self, mock_app, db):
        """Should return balance for existing user."""
        from engine.api.routes import get_user_balance

        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index, arena_balance) "
            "VALUES (?, ?, ?, ?)",
            ("user-001", "0.0.1001", 0, 45000.0),
        )

        request = _make_request(mock_app)
        result = await get_user_balance("user-001", request)

        assert result["user_id"] == "user-001"
        assert result["arena_balance"] == 45000.0
        assert result["hedera_account_id"] == "0.0.1001"

    @pytest.mark.asyncio
    async def test_user_not_found(self, mock_app, db):
        """Should return error tuple for non-existent user."""
        from engine.api.routes import get_user_balance

        request = _make_request(mock_app)
        result = await get_user_balance("nonexistent", request)

        # The endpoint returns a tuple (dict, status_code) for errors
        assert result == ({"error": "User not found"}, 404)


class TestAllocateWithUser:
    """Tests for POST /api/allocate with user_id."""

    @pytest.mark.asyncio
    async def test_user_allocation_deducts_balance(self, mock_app, db):
        """Should deduct amount from user's arena_balance."""
        from engine.api.routes import allocate_capital

        # Setup: user + agent + season
        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index, arena_balance) "
            "VALUES (?, ?, ?, ?)",
            ("user-001", "0.0.1001", 0, 50000.0),
        )
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id, wallet_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("agent-001", "Bot", "thesis", "prompt", "0.0.2001", 5),
        )
        await db.execute(
            "INSERT INTO seasons (id, status) VALUES (?, ?)", (1, "active")
        )

        hedera = mock_app.state.hedera_client
        hedera.transfer_user_to_agent = AsyncMock(return_value="tx-alloc-001")

        request = _make_request(mock_app, {
            "user_id": "user-001",
            "agent_id": "agent-001",
            "amount": 5000.0,
        })
        result = await allocate_capital(request)

        assert result["hedera_tx_id"] == "tx-alloc-001"

        # Verify balance was deducted
        user = await db.fetchone("SELECT * FROM users WHERE id = ?", ("user-001",))
        assert user["arena_balance"] == 45000.0

    @pytest.mark.asyncio
    async def test_user_allocation_insufficient_balance(self, mock_app, db):
        """Should reject allocation when user has insufficient balance."""
        from engine.api.routes import allocate_capital
        from fastapi import HTTPException

        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index, arena_balance) "
            "VALUES (?, ?, ?, ?)",
            ("user-001", "0.0.1001", 0, 100.0),
        )
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agent-001", "Bot", "thesis", "prompt", "0.0.2001"),
        )

        request = _make_request(mock_app, {
            "user_id": "user-001",
            "agent_id": "agent-001",
            "amount": 5000.0,
        })

        with pytest.raises(HTTPException) as exc_info:
            await allocate_capital(request)
        assert exc_info.value.status_code == 400
        assert "Insufficient" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_user_allocation_user_not_found(self, mock_app, db):
        """Should reject allocation when user_id doesn't exist."""
        from engine.api.routes import allocate_capital
        from fastapi import HTTPException

        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agent-001", "Bot", "thesis", "prompt", "0.0.2001"),
        )

        request = _make_request(mock_app, {
            "user_id": "nonexistent",
            "agent_id": "agent-001",
            "amount": 1000.0,
        })

        with pytest.raises(HTTPException) as exc_info:
            await allocate_capital(request)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_allocation_records_user_id(self, mock_app, db):
        """Should store user_id in the allocations table."""
        from engine.api.routes import allocate_capital

        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index, arena_balance) "
            "VALUES (?, ?, ?, ?)",
            ("user-001", "0.0.1001", 0, 50000.0),
        )
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id, wallet_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("agent-001", "Bot", "thesis", "prompt", "0.0.2001", 5),
        )
        await db.execute(
            "INSERT INTO seasons (id, status) VALUES (?, ?)", (1, "active")
        )

        hedera = mock_app.state.hedera_client
        hedera.transfer_user_to_agent = AsyncMock(return_value="tx-alloc-002")

        request = _make_request(mock_app, {
            "user_id": "user-001",
            "agent_id": "agent-001",
            "amount": 2000.0,
        })
        await allocate_capital(request)

        alloc = await db.fetchone(
            "SELECT * FROM allocations WHERE agent_id = ?", ("agent-001",)
        )
        assert alloc is not None
        assert alloc["user_id"] == "user-001"

    @pytest.mark.asyncio
    async def test_legacy_allocation_without_user(self, mock_app, db):
        """Allocation without user_id should still work (backward compatible)."""
        from engine.api.routes import allocate_capital

        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agent-001", "Bot", "thesis", "prompt", "0.0.2001"),
        )
        await db.execute(
            "INSERT INTO seasons (id, status) VALUES (?, ?)", (1, "active")
        )

        hedera = mock_app.state.hedera_client
        hedera.allocate_capital = AsyncMock(return_value="tx-legacy-001")

        request = _make_request(mock_app, {
            "agent_id": "agent-001",
            "amount": 1000.0,
        })
        result = await allocate_capital(request)

        assert result["hedera_tx_id"] == "tx-legacy-001"


class TestCreateAgentWithUser:
    """Tests for POST /api/agents/create with user_id."""

    @pytest.mark.asyncio
    async def test_agent_creation_deducts_1000_arena(self, mock_app, db):
        """Should deduct 1000 ARENA from user for agent creation."""
        from engine.api.routes import create_agent_endpoint

        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index, arena_balance) "
            "VALUES (?, ?, ?, ?)",
            ("user-001", "0.0.1001", 0, 50000.0),
        )

        # Mock create_agent to avoid LLM calls
        mock_agent = MagicMock()
        mock_agent.id = "agent-123"
        mock_agent.name = "TestBot"
        mock_agent.thesis = "buy the dip"
        mock_agent.system_prompt = "you are a trader"
        mock_agent.hedera_account_id = "0.0.2001"
        mock_agent.creator_name = "user-001"
        mock_agent.is_preset = False

        with patch("engine.api.routes.create_agent", new_callable=AsyncMock, return_value=mock_agent):
            request = _make_request(mock_app, {
                "thesis": "buy the dip",
                "creator_name": "tester",
                "user_id": "user-001",
            })
            result = await create_agent_endpoint(request)

        assert result["id"] == "agent-123"

        user = await db.fetchone("SELECT * FROM users WHERE id = ?", ("user-001",))
        assert user["arena_balance"] == 49000.0

    @pytest.mark.asyncio
    async def test_agent_creation_insufficient_balance(self, mock_app, db):
        """Should reject agent creation when user has < 1000 ARENA."""
        from engine.api.routes import create_agent_endpoint
        from fastapi import HTTPException

        await db.execute(
            "INSERT INTO users (id, hedera_account_id, wallet_index, arena_balance) "
            "VALUES (?, ?, ?, ?)",
            ("user-001", "0.0.1001", 0, 500.0),
        )

        request = _make_request(mock_app, {
            "thesis": "buy the dip",
            "user_id": "user-001",
        })

        with pytest.raises(HTTPException) as exc_info:
            await create_agent_endpoint(request)
        assert exc_info.value.status_code == 400
        assert "1000 ARENA" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_agent_creation_without_user_id(self, mock_app, db):
        """Agent creation without user_id should still work (no cost)."""
        from engine.api.routes import create_agent_endpoint

        mock_agent = MagicMock()
        mock_agent.id = "agent-456"
        mock_agent.name = "FreeBot"
        mock_agent.thesis = "hodl"
        mock_agent.system_prompt = "you are a hodler"
        mock_agent.hedera_account_id = "0.0.3001"
        mock_agent.creator_name = None
        mock_agent.is_preset = False

        with patch("engine.api.routes.create_agent", new_callable=AsyncMock, return_value=mock_agent):
            request = _make_request(mock_app, {
                "thesis": "hodl",
            })
            result = await create_agent_endpoint(request)

        assert result["id"] == "agent-456"

    @pytest.mark.asyncio
    async def test_agent_creation_accepts_instruments_and_model(self, mock_app, db):
        """Should accept optional instruments and model fields without error."""
        from engine.api.routes import create_agent_endpoint

        mock_agent = MagicMock()
        mock_agent.id = "agent-789"
        mock_agent.name = "CustomBot"
        mock_agent.thesis = "arbitrage"
        mock_agent.system_prompt = "you trade"
        mock_agent.hedera_account_id = "0.0.4001"
        mock_agent.creator_name = "tester"
        mock_agent.is_preset = False

        with patch("engine.api.routes.create_agent", new_callable=AsyncMock, return_value=mock_agent):
            request = _make_request(mock_app, {
                "thesis": "arbitrage",
                "creator_name": "tester",
                "instruments": ["HBAR", "BTC"],
                "model": "gpt-4",
            })
            result = await create_agent_endpoint(request)

        assert result["id"] == "agent-789"
