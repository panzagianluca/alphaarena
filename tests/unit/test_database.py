"""
Tests for engine.db.database — the async SQLite database layer.

Covers: init, WAL mode, foreign keys, CRUD operations, dict-style rows,
schema creation (all 7 tables), and edge cases.
"""

from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio

from engine.db.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    """Provide an initialized Database pointing at a temp file."""
    db_path = str(tmp_path / "test.db")
    database = Database(db_path=db_path)
    await database.init()
    yield database
    await database.close()


# ---- Initialization & Pragmas ----


@pytest.mark.asyncio
async def test_init_creates_db_file(tmp_path):
    db_path = str(tmp_path / "new.db")
    assert not os.path.exists(db_path)
    database = Database(db_path=db_path)
    await database.init()
    assert os.path.exists(db_path)
    await database.close()


@pytest.mark.asyncio
async def test_wal_mode_enabled(db):
    row = await db.fetchone("PRAGMA journal_mode")
    assert row is not None
    assert row["journal_mode"] == "wal"


@pytest.mark.asyncio
async def test_foreign_keys_enabled(db):
    row = await db.fetchone("PRAGMA foreign_keys")
    assert row is not None
    assert row["foreign_keys"] == 1


# ---- Schema: All 8 tables exist ----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "table_name",
    ["agents", "seasons", "trades", "portfolios", "leaderboard", "allocations", "commentary", "users"],
)
async def test_table_exists(db, table_name):
    row = await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    assert row is not None, f"Table '{table_name}' was not created"


@pytest.mark.asyncio
async def test_init_is_idempotent(tmp_path):
    """Calling init() twice should not fail (CREATE TABLE IF NOT EXISTS)."""
    db_path = str(tmp_path / "idem.db")
    database = Database(db_path=db_path)
    await database.init()
    # Insert data
    await database.execute(
        "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
        ("a1", "Bot", "thesis", "prompt"),
    )
    await database.close()

    # Re-open and re-init
    database2 = Database(db_path=db_path)
    await database2.init()
    agent = await database2.fetchone("SELECT * FROM agents WHERE id = ?", ("a1",))
    assert agent is not None
    assert agent["name"] == "Bot"
    await database2.close()


# ---- CRUD: agents ----


@pytest.mark.asyncio
async def test_insert_and_read_agent(db):
    await db.execute(
        """INSERT INTO agents (id, name, thesis, system_prompt, creator_name, is_preset)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("agent-1", "EthMaxi", "Buy ETH dips", "You are EthMaxi.", "alice", 0),
    )
    agent = await db.fetchone("SELECT * FROM agents WHERE id = ?", ("agent-1",))
    assert agent is not None
    assert agent["id"] == "agent-1"
    assert agent["name"] == "EthMaxi"
    assert agent["thesis"] == "Buy ETH dips"
    assert agent["status"] == "active"
    assert agent["is_preset"] == 0


@pytest.mark.asyncio
async def test_fetchone_returns_none_for_missing(db):
    result = await db.fetchone("SELECT * FROM agents WHERE id = ?", ("nonexistent",))
    assert result is None


@pytest.mark.asyncio
async def test_fetchall_returns_list_of_dicts(db):
    for i in range(3):
        await db.execute(
            "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
            (f"a{i}", f"Bot{i}", "thesis", "prompt"),
        )
    agents = await db.fetchall("SELECT * FROM agents ORDER BY id")
    assert len(agents) == 3
    assert isinstance(agents[0], dict)
    assert agents[0]["id"] == "a0"
    assert agents[2]["id"] == "a2"


@pytest.mark.asyncio
async def test_fetchall_returns_empty_list(db):
    result = await db.fetchall("SELECT * FROM agents")
    assert result == []


# ---- CRUD: seasons ----


@pytest.mark.asyncio
async def test_insert_season(db):
    await db.execute(
        "INSERT INTO seasons (status, total_rounds) VALUES (?, ?)",
        ("active", 30),
    )
    season = await db.fetchone("SELECT * FROM seasons WHERE id = 1")
    assert season is not None
    assert season["status"] == "active"
    assert season["total_rounds"] == 30
    assert season["rounds_completed"] == 0


# ---- CRUD: trades ----


@pytest.mark.asyncio
async def test_insert_trade(db):
    # Need an agent and season first (foreign keys)
    await db.execute(
        "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
        ("a1", "Bot", "thesis", "prompt"),
    )
    await db.execute(
        "INSERT INTO seasons (status) VALUES (?)",
        ("active",),
    )
    await db.execute(
        """INSERT INTO trades
           (season_id, agent_id, round_number, action, asset, amount_pct,
            amount_tokens, price_at_trade, reasoning, confidence, mood,
            hedera_tx_id, hcs_tx_id, portfolio_value_after)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, "a1", 1, "buy", "ETH", 25.0, 0.65, 3850.0,
         "ETH dipped, buying", 0.8, "bullish", "0.0.123@456", "0.0.789@012", 10000.0),
    )
    trade = await db.fetchone("SELECT * FROM trades WHERE id = 1")
    assert trade is not None
    assert trade["action"] == "buy"
    assert trade["asset"] == "ETH"
    assert trade["hcs_tx_id"] == "0.0.789@012"


# ---- CRUD: portfolios (composite PK) ----


@pytest.mark.asyncio
async def test_insert_portfolio(db):
    await db.execute(
        "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
        ("a1", "Bot", "thesis", "prompt"),
    )
    await db.execute("INSERT INTO seasons (status) VALUES (?)", ("active",))
    await db.execute(
        "INSERT INTO portfolios (agent_id, season_id, asset, units, avg_entry_price) VALUES (?, ?, ?, ?, ?)",
        ("a1", 1, "ETH", 2.5, 3800.0),
    )
    row = await db.fetchone(
        "SELECT * FROM portfolios WHERE agent_id = ? AND season_id = ? AND asset = ?",
        ("a1", 1, "ETH"),
    )
    assert row is not None
    assert row["units"] == 2.5
    assert row["avg_entry_price"] == 3800.0


# ---- CRUD: leaderboard (composite PK) ----


@pytest.mark.asyncio
async def test_insert_leaderboard(db):
    await db.execute(
        "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
        ("a1", "Bot", "thesis", "prompt"),
    )
    await db.execute("INSERT INTO seasons (status) VALUES (?)", ("active",))
    await db.execute(
        """INSERT INTO leaderboard
           (agent_id, season_id, total_pnl_usd, pnl_pct, sharpe_ratio,
            win_rate, max_drawdown_pct, total_trades, rank)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("a1", 1, 500.0, 5.0, 1.2, 60.0, 8.5, 15, 1),
    )
    row = await db.fetchone(
        "SELECT * FROM leaderboard WHERE agent_id = ? AND season_id = ?",
        ("a1", 1),
    )
    assert row is not None
    assert row["pnl_pct"] == 5.0
    assert row["rank"] == 1


# ---- CRUD: allocations ----


@pytest.mark.asyncio
async def test_insert_allocation(db):
    await db.execute(
        "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
        ("a1", "Bot", "thesis", "prompt"),
    )
    await db.execute("INSERT INTO seasons (status) VALUES (?)", ("active",))
    await db.execute(
        "INSERT INTO allocations (agent_id, season_id, amount, hedera_tx_id) VALUES (?, ?, ?, ?)",
        ("a1", 1, 1000.0, "0.0.123@456"),
    )
    row = await db.fetchone("SELECT * FROM allocations WHERE id = 1")
    assert row is not None
    assert row["amount"] == 1000.0


# ---- CRUD: commentary ----


@pytest.mark.asyncio
async def test_insert_commentary(db):
    await db.execute("INSERT INTO seasons (status) VALUES (?)", ("active",))
    await db.execute(
        "INSERT INTO commentary (season_id, round_number, content) VALUES (?, ?, ?)",
        (1, 5, "EthMaxi is on a tear!"),
    )
    row = await db.fetchone("SELECT * FROM commentary WHERE id = 1")
    assert row is not None
    assert row["content"] == "EthMaxi is on a tear!"
    assert row["round_number"] == 5


# ---- Update and delete ----


@pytest.mark.asyncio
async def test_update_agent_status(db):
    await db.execute(
        "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
        ("a1", "Bot", "thesis", "prompt"),
    )
    await db.execute("UPDATE agents SET status = ? WHERE id = ?", ("retired", "a1"))
    agent = await db.fetchone("SELECT * FROM agents WHERE id = ?", ("a1",))
    assert agent is not None
    assert agent["status"] == "retired"


@pytest.mark.asyncio
async def test_delete_agent(db):
    await db.execute(
        "INSERT INTO agents (id, name, thesis, system_prompt) VALUES (?, ?, ?, ?)",
        ("a1", "Bot", "thesis", "prompt"),
    )
    await db.execute("DELETE FROM agents WHERE id = ?", ("a1",))
    agent = await db.fetchone("SELECT * FROM agents WHERE id = ?", ("a1",))
    assert agent is None


# ---- Error handling: uninitialized DB ----


@pytest.mark.asyncio
async def test_execute_before_init_raises(tmp_path):
    database = Database(db_path=str(tmp_path / "uninit.db"))
    with pytest.raises(AssertionError, match="not initialized"):
        await database.execute("SELECT 1")


@pytest.mark.asyncio
async def test_fetchone_before_init_raises(tmp_path):
    database = Database(db_path=str(tmp_path / "uninit.db"))
    with pytest.raises(AssertionError, match="not initialized"):
        await database.fetchone("SELECT 1")


@pytest.mark.asyncio
async def test_fetchall_before_init_raises(tmp_path):
    database = Database(db_path=str(tmp_path / "uninit.db"))
    with pytest.raises(AssertionError, match="not initialized"):
        await database.fetchall("SELECT 1")


# ---- Close ----


@pytest.mark.asyncio
async def test_close_sets_conn_to_none(tmp_path):
    database = Database(db_path=str(tmp_path / "close.db"))
    await database.init()
    assert database._conn is not None
    await database.close()
    assert database._conn is None


@pytest.mark.asyncio
async def test_close_when_not_opened(tmp_path):
    """Closing a never-opened database should not raise."""
    database = Database(db_path=str(tmp_path / "never.db"))
    await database.close()  # should be a no-op
