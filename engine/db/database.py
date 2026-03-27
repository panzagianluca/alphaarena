"""
Async SQLite database layer for Agent League.

Uses aiosqlite for non-blocking access. No ORM — raw SQL only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """Thin async wrapper around aiosqlite with dict-style rows."""

    def __init__(self, db_path: str = "league.db") -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open connection, enable WAL + foreign keys, create tables from schema.sql."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

        schema_sql = SCHEMA_PATH.read_text()
        await self._conn.executescript(schema_sql)
        await self._conn.commit()

    async def execute(self, sql: str, params: tuple = ()) -> None:
        """Run a write operation (INSERT, UPDATE, DELETE) and auto-commit."""
        assert self._conn is not None, "Database not initialized. Call init() first."
        await self._conn.execute(sql, params)
        await self._conn.commit()

    async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict, or None if no match."""
        assert self._conn is not None, "Database not initialized. Call init() first."
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        """Fetch all matching rows as a list of dicts."""
        assert self._conn is not None, "Database not initialized. Call init() first."
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Quick self-test: init DB, insert a test agent, read it back, clean up.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os

    TEST_DB = "test_league.db"

    async def _self_test() -> None:
        db = Database(db_path=TEST_DB)
        await db.init()

        # Verify WAL mode
        row = await db.fetchone("PRAGMA journal_mode")
        assert row is not None
        print(f"journal_mode = {row['journal_mode']}")
        assert row["journal_mode"] == "wal", f"Expected WAL, got {row['journal_mode']}"

        # Insert a test agent
        await db.execute(
            """
            INSERT INTO agents (id, name, thesis, system_prompt, creator_name, is_preset)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("test-001", "TestBot", "Buy everything", "You are TestBot.", "tester", 0),
        )

        # Read it back
        agent = await db.fetchone("SELECT * FROM agents WHERE id = ?", ("test-001",))
        assert agent is not None
        assert agent["name"] == "TestBot"
        assert agent["thesis"] == "Buy everything"
        assert agent["status"] == "active"
        print(f"Agent read back: {dict(agent)}")

        # Verify fetchall
        agents = await db.fetchall("SELECT * FROM agents")
        assert len(agents) == 1
        print(f"Total agents: {len(agents)}")

        await db.close()
        print("All self-tests passed.")

    try:
        asyncio.run(_self_test())
    finally:
        # Clean up test database file
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
            print(f"Cleaned up {TEST_DB}")
        # WAL mode can leave -wal and -shm files
        for suffix in ("-wal", "-shm"):
            path = TEST_DB + suffix
            if os.path.exists(path):
                os.remove(path)
