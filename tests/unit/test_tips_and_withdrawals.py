"""
Tests for payment features: Agent-to-Agent Tips and User Withdrawals.

Feature 1: Tips
- Schema: tips table exists with correct columns
- Orchestrator._distribute_tips() sends tips from top agent to 2nd/3rd
- Tips are recorded in DB with correct amounts
- Tips broadcast via WebSocket
- Graceful failure when < 3 agents
- GET /api/tips endpoint returns recent tips

Feature 2: Withdrawals
- Schema: allocations table has `withdrawn` column
- POST /api/withdraw calculates proportional returns
- Withdrawal updates user arena_balance
- Withdrawal marks allocation as withdrawn
- Cannot withdraw twice (already withdrawn)
- GET /api/user/{user_id}/withdrawable returns allocation values
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


@pytest_asyncio.fixture
async def seeded_db(db):
    """DB with agents, a season, leaderboard entries, users, and allocations."""
    # Create 3 agents
    for i, (aid, name, thesis) in enumerate([
        ("agent-001", "AlphaBot", "Buy low sell high"),
        ("agent-002", "BetaBot", "Follow momentum"),
        ("agent-003", "GammaBot", "Contrarian plays"),
    ]):
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id, wallet_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (aid, name, thesis, f"You are {name}", f"0.0.100{i+1}", i),
        )

    # Create a season
    await db.execute(
        "INSERT INTO seasons (status, total_rounds, started_at) VALUES ('active', 30, '2026-01-01')"
    )

    # Leaderboard: agent-001 is rank 1, agent-002 is rank 2, agent-003 is rank 3
    for aid, rank, pnl_pct in [
        ("agent-001", 1, 15.5),
        ("agent-002", 2, 8.2),
        ("agent-003", 3, -2.1),
    ]:
        await db.execute(
            "INSERT INTO leaderboard (agent_id, season_id, pnl_pct, rank) VALUES (?, 1, ?, ?)",
            (aid, pnl_pct, rank),
        )

    # Create a user
    await db.execute(
        "INSERT INTO users (id, name, hedera_account_id, wallet_index, arena_balance) "
        "VALUES (?, ?, ?, ?, ?)",
        ("user-001", "TestUser", "0.0.2001", 10, 50000.0),
    )

    # Create allocations from user to agents
    await db.execute(
        "INSERT INTO allocations (agent_id, season_id, amount, user_id, hedera_tx_id) "
        "VALUES (?, 1, ?, ?, ?)",
        ("agent-001", 5000.0, "user-001", "0.0.9999@1234567890.000"),
    )
    await db.execute(
        "INSERT INTO allocations (agent_id, season_id, amount, user_id, hedera_tx_id) "
        "VALUES (?, 1, ?, ?, ?)",
        ("agent-002", 3000.0, "user-001", "0.0.9999@1234567891.000"),
    )

    return db


# ===========================================================================
# Feature 1: Tips - Schema Tests
# ===========================================================================

class TestTipsSchema:
    """Verify the tips table exists with correct columns."""

    @pytest.mark.asyncio
    async def test_tips_table_exists(self, db):
        row = await db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tips'"
        )
        assert row is not None, "Table 'tips' was not created"

    @pytest.mark.asyncio
    async def test_tips_table_columns(self, db):
        """Tips table should have all required columns."""
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
            ("a1", "Bot1", "thesis", "prompt"),
        )
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
            ("a2", "Bot2", "thesis", "prompt"),
        )
        await db.execute(
            "INSERT INTO tips (from_agent_id, to_agent_id, amount, season_id, hedera_tx_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("a1", "a2", 50.0, 1, "0.0.9999@123.000"),
        )
        tip = await db.fetchone("SELECT * FROM tips WHERE id = 1")
        assert tip is not None
        assert tip["from_agent_id"] == "a1"
        assert tip["to_agent_id"] == "a2"
        assert tip["amount"] == 50.0
        assert tip["season_id"] == 1
        assert tip["hedera_tx_id"] == "0.0.9999@123.000"
        assert "timestamp" in tip


# ===========================================================================
# Feature 1: Tips - Orchestrator._distribute_tips()
# ===========================================================================

class TestDistributeTips:
    """Test the _distribute_tips method on Orchestrator."""

    @pytest.mark.asyncio
    async def test_distribute_tips_sends_correct_amounts(self, seeded_db):
        """Top agent tips 50 aUSD to 2nd, 25 aUSD to 3rd."""
        from engine.core.orchestrator import Orchestrator

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value="0.0.9999@tip.000")

        orch = Orchestrator(
            db=seeded_db,
            hedera=mock_hedera,
            market=MagicMock(),
            portfolio=MagicMock(),
        )
        orch.season_id = 1
        orch.broadcast_callback = AsyncMock()

        await orch._distribute_tips()

        # Should have called fund_agent twice: once for 2nd place, once for 3rd
        assert mock_hedera.fund_agent.call_count == 2
        calls = mock_hedera.fund_agent.call_args_list

        # Tip to 2nd place (agent-002, account 0.0.1002): 50
        assert calls[0].args == ("0.0.1002", 50)
        # Tip to 3rd place (agent-003, account 0.0.1003): 25
        assert calls[1].args == ("0.0.1003", 25)

    @pytest.mark.asyncio
    async def test_distribute_tips_records_in_db(self, seeded_db):
        """Tips should be recorded in the tips table."""
        from engine.core.orchestrator import Orchestrator

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value="0.0.9999@tip.000")

        orch = Orchestrator(
            db=seeded_db,
            hedera=mock_hedera,
            market=MagicMock(),
            portfolio=MagicMock(),
        )
        orch.season_id = 1
        orch.broadcast_callback = AsyncMock()

        await orch._distribute_tips()

        tips = await seeded_db.fetchall("SELECT * FROM tips ORDER BY amount DESC")
        assert len(tips) == 2

        # 50 aUSD tip from agent-001 to agent-002
        assert tips[0]["from_agent_id"] == "agent-001"
        assert tips[0]["to_agent_id"] == "agent-002"
        assert tips[0]["amount"] == 50.0
        assert tips[0]["season_id"] == 1
        assert tips[0]["hedera_tx_id"] == "0.0.9999@tip.000"

        # 25 aUSD tip from agent-001 to agent-003
        assert tips[1]["from_agent_id"] == "agent-001"
        assert tips[1]["to_agent_id"] == "agent-003"
        assert tips[1]["amount"] == 25.0

    @pytest.mark.asyncio
    async def test_distribute_tips_broadcasts_events(self, seeded_db):
        """Tip events should be broadcast via WebSocket."""
        from engine.core.orchestrator import Orchestrator

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value="0.0.9999@tip.000")

        broadcast_mock = AsyncMock()
        orch = Orchestrator(
            db=seeded_db,
            hedera=mock_hedera,
            market=MagicMock(),
            portfolio=MagicMock(),
        )
        orch.season_id = 1
        orch.broadcast_callback = broadcast_mock

        await orch._distribute_tips()

        # Should have broadcast tip events
        assert broadcast_mock.call_count >= 1
        # Find the tip broadcast
        tip_broadcasts = [
            call for call in broadcast_mock.call_args_list
            if call.args[0].get("type") == "tips"
        ]
        assert len(tip_broadcasts) == 1
        tip_data = tip_broadcasts[0].args[0]["data"]
        assert len(tip_data) == 2

    @pytest.mark.asyncio
    async def test_distribute_tips_fewer_than_3_agents(self, db):
        """Should not crash when fewer than 3 agents exist."""
        from engine.core.orchestrator import Orchestrator

        # Only 2 agents
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("a1", "Bot1", "t", "p", "0.0.1001"),
        )
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt, hedera_account_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("a2", "Bot2", "t", "p", "0.0.1002"),
        )
        await db.execute(
            "INSERT INTO seasons (status) VALUES ('active')"
        )
        await db.execute(
            "INSERT INTO leaderboard (agent_id, season_id, rank, pnl_pct) VALUES (?, 1, 1, 10.0)",
            ("a1",),
        )
        await db.execute(
            "INSERT INTO leaderboard (agent_id, season_id, rank, pnl_pct) VALUES (?, 1, 2, 5.0)",
            ("a2",),
        )

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value="tx123")

        orch = Orchestrator(
            db=db,
            hedera=mock_hedera,
            market=MagicMock(),
            portfolio=MagicMock(),
        )
        orch.season_id = 1
        orch.broadcast_callback = AsyncMock()

        # Should not raise
        await orch._distribute_tips()

        # Should only tip the one agent that exists (2nd place)
        assert mock_hedera.fund_agent.call_count == 1

    @pytest.mark.asyncio
    async def test_distribute_tips_hedera_failure_graceful(self, seeded_db):
        """If Hedera call fails, tip should still be recorded with None tx_id."""
        from engine.core.orchestrator import Orchestrator

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value=None)

        orch = Orchestrator(
            db=seeded_db,
            hedera=mock_hedera,
            market=MagicMock(),
            portfolio=MagicMock(),
        )
        orch.season_id = 1
        orch.broadcast_callback = AsyncMock()

        await orch._distribute_tips()

        tips = await seeded_db.fetchall("SELECT * FROM tips")
        assert len(tips) == 2
        # tx_id should be None
        assert tips[0]["hedera_tx_id"] is None


# ===========================================================================
# Feature 1: Tips - GET /api/tips endpoint
# ===========================================================================

class TestTipsEndpoint:
    """Test the GET /api/tips endpoint."""

    @pytest.mark.asyncio
    async def test_get_tips_returns_recent(self, seeded_db):
        """GET /api/tips should return recent tips with agent names."""
        # Insert some tips
        await seeded_db.execute(
            "INSERT INTO tips (from_agent_id, to_agent_id, amount, season_id, hedera_tx_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agent-001", "agent-002", 50.0, 1, "tx1"),
        )
        await seeded_db.execute(
            "INSERT INTO tips (from_agent_id, to_agent_id, amount, season_id, hedera_tx_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agent-001", "agent-003", 25.0, 1, "tx2"),
        )

        # Import and call the route handler directly
        from engine.api.routes import get_tips

        # Mock request
        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db

        result = await get_tips(mock_request)
        assert isinstance(result, list)
        assert len(result) == 2
        # Should include agent names via JOIN
        assert result[0]["from_agent_name"] is not None
        assert result[0]["to_agent_name"] is not None


# ===========================================================================
# Feature 2: Withdrawals - Schema Tests
# ===========================================================================

class TestWithdrawalSchema:
    """Verify schema changes for withdrawal support."""

    @pytest.mark.asyncio
    async def test_allocations_has_withdrawn_column(self, db):
        """Allocations table should have a `withdrawn` column defaulting to 0."""
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
            ("a1", "Bot", "t", "p"),
        )
        await db.execute(
            "INSERT INTO seasons (status) VALUES ('active')"
        )
        await db.execute(
            "INSERT INTO allocations (agent_id, season_id, amount, user_id) "
            "VALUES (?, 1, 1000, ?)",
            ("a1", "user-001"),
        )
        alloc = await db.fetchone("SELECT * FROM allocations WHERE id = 1")
        assert alloc is not None
        assert alloc["withdrawn"] == 0


# ===========================================================================
# Feature 2: Withdrawals - POST /api/withdraw
# ===========================================================================

class TestWithdrawEndpoint:
    """Test the POST /api/withdraw endpoint."""

    @pytest.mark.asyncio
    async def test_withdraw_calculates_returns(self, seeded_db):
        """Withdrawal should calculate returns based on agent P&L."""
        from engine.api.routes import withdraw

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value="0.0.9999@withdraw.000")

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db
        mock_request.app.state.hedera_client = mock_hedera
        mock_request.app.state.orchestrator = MagicMock()
        mock_request.app.state.orchestrator.broadcast_callback = None
        mock_request.json = AsyncMock(return_value={
            "user_id": "user-001",
            "agent_id": "agent-001",
        })

        result = await withdraw(mock_request)

        # agent-001 has pnl_pct=15.5, allocation=5000
        # return_amount = 5000 * (1 + 15.5/100) = 5000 * 1.155 = 5775.0
        assert result["original_amount"] == 5000.0
        assert result["return_amount"] == 5775.0
        assert result["profit"] == 775.0
        assert result["hedera_tx_id"] == "0.0.9999@withdraw.000"

    @pytest.mark.asyncio
    async def test_withdraw_updates_user_balance(self, seeded_db):
        """Withdrawal should credit user's arena_balance."""
        from engine.api.routes import withdraw

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value="0.0.9999@withdraw.000")

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db
        mock_request.app.state.hedera_client = mock_hedera
        mock_request.app.state.orchestrator = MagicMock()
        mock_request.app.state.orchestrator.broadcast_callback = None
        mock_request.json = AsyncMock(return_value={
            "user_id": "user-001",
            "agent_id": "agent-001",
        })

        await withdraw(mock_request)

        user = await seeded_db.fetchone("SELECT * FROM users WHERE id = 'user-001'")
        # Original 50000 + 5775 return = 55775
        assert user["arena_balance"] == 55775.0

    @pytest.mark.asyncio
    async def test_withdraw_marks_allocation_withdrawn(self, seeded_db):
        """Withdrawal should set withdrawn=1 on the allocation."""
        from engine.api.routes import withdraw

        mock_hedera = MagicMock()
        mock_hedera.fund_agent = AsyncMock(return_value="tx-abc")

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db
        mock_request.app.state.hedera_client = mock_hedera
        mock_request.app.state.orchestrator = MagicMock()
        mock_request.app.state.orchestrator.broadcast_callback = None
        mock_request.json = AsyncMock(return_value={
            "user_id": "user-001",
            "agent_id": "agent-001",
        })

        await withdraw(mock_request)

        alloc = await seeded_db.fetchone(
            "SELECT * FROM allocations WHERE agent_id = 'agent-001' AND user_id = 'user-001'"
        )
        assert alloc["withdrawn"] == 1

    @pytest.mark.asyncio
    async def test_withdraw_already_withdrawn_raises(self, seeded_db):
        """Cannot withdraw the same allocation twice."""
        from engine.api.routes import withdraw
        from fastapi import HTTPException

        # Mark allocation as already withdrawn
        await seeded_db.execute(
            "UPDATE allocations SET withdrawn = 1 WHERE agent_id = 'agent-001' AND user_id = 'user-001'"
        )

        mock_hedera = MagicMock()
        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db
        mock_request.app.state.hedera_client = mock_hedera
        mock_request.app.state.orchestrator = MagicMock()
        mock_request.app.state.orchestrator.broadcast_callback = None
        mock_request.json = AsyncMock(return_value={
            "user_id": "user-001",
            "agent_id": "agent-001",
        })

        with pytest.raises(HTTPException) as exc_info:
            await withdraw(mock_request)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_withdraw_user_not_found_raises(self, seeded_db):
        """Withdrawal with unknown user_id should raise 404."""
        from engine.api.routes import withdraw
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db
        mock_request.app.state.hedera_client = MagicMock()
        mock_request.app.state.orchestrator = MagicMock()
        mock_request.app.state.orchestrator.broadcast_callback = None
        mock_request.json = AsyncMock(return_value={
            "user_id": "nonexistent",
            "agent_id": "agent-001",
        })

        with pytest.raises(HTTPException) as exc_info:
            await withdraw(mock_request)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_withdraw_no_allocation_raises(self, seeded_db):
        """Withdrawal with no matching allocation should raise 404."""
        from engine.api.routes import withdraw
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db
        mock_request.app.state.hedera_client = MagicMock()
        mock_request.app.state.orchestrator = MagicMock()
        mock_request.app.state.orchestrator.broadcast_callback = None
        mock_request.json = AsyncMock(return_value={
            "user_id": "user-001",
            "agent_id": "agent-003",  # no allocation for this agent
        })

        with pytest.raises(HTTPException) as exc_info:
            await withdraw(mock_request)
        assert exc_info.value.status_code == 404


# ===========================================================================
# Feature 2: Withdrawals - GET /api/user/{user_id}/withdrawable
# ===========================================================================

class TestWithdrawableEndpoint:
    """Test the GET /api/user/{user_id}/withdrawable endpoint."""

    @pytest.mark.asyncio
    async def test_withdrawable_returns_allocations_with_values(self, seeded_db):
        """Should return list of non-withdrawn allocations with current value."""
        from engine.api.routes import get_withdrawable

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db

        result = await get_withdrawable("user-001", mock_request)

        assert isinstance(result, list)
        assert len(result) == 2

        # Find the agent-001 allocation
        a001 = next(a for a in result if a["agent_id"] == "agent-001")
        assert a001["original_amount"] == 5000.0
        # agent-001 pnl_pct = 15.5 -> current_value = 5000 * 1.155 = 5775
        assert a001["current_value"] == 5775.0
        assert a001["profit"] == 775.0

        # Find the agent-002 allocation
        a002 = next(a for a in result if a["agent_id"] == "agent-002")
        assert a002["original_amount"] == 3000.0
        # agent-002 pnl_pct = 8.2 -> current_value = 3000 * 1.082 = 3246
        assert a002["current_value"] == 3246.0
        assert a002["profit"] == 246.0

    @pytest.mark.asyncio
    async def test_withdrawable_excludes_withdrawn(self, seeded_db):
        """Already-withdrawn allocations should not appear."""
        from engine.api.routes import get_withdrawable

        # Mark one as withdrawn
        await seeded_db.execute(
            "UPDATE allocations SET withdrawn = 1 WHERE agent_id = 'agent-001' AND user_id = 'user-001'"
        )

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db

        result = await get_withdrawable("user-001", mock_request)
        assert len(result) == 1
        assert result[0]["agent_id"] == "agent-002"

    @pytest.mark.asyncio
    async def test_withdrawable_user_not_found(self, seeded_db):
        """Should raise 404 for unknown user."""
        from engine.api.routes import get_withdrawable
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.app.state.db = seeded_db

        with pytest.raises(HTTPException) as exc_info:
            await get_withdrawable("nonexistent", mock_request)
        assert exc_info.value.status_code == 404
