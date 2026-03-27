"""
Agent creation & loading for Agent League.

Functions
---------
create_agent   — generate persona via LLM, assign wallet, fund ARENA, persist.
load_agents    — read all active agents from DB (+ private keys from wallet pool).
seed_presets   — ensure the 4 preset agents exist (idempotent).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from uuid import uuid4

from engine.agents.base import TradingAgent
from engine.agents.templates import PRESET_THESES
from engine.core.llm import thesis_to_prompt
from engine.db.database import Database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_id(name: str) -> str:
    """Slugify agent name + short random suffix.  e.g. 'ethmxi-a3f2'."""
    slug = re.sub(r"[^a-z0-9]", "", name.lower())[:10]
    suffix = uuid4().hex[:4]
    return f"{slug}-{suffix}"


def _load_wallet_pool() -> list[dict[str, Any]]:
    """Read wallets.json from the path specified by WALLET_POOL_PATH env var."""
    wallet_path = os.environ.get("WALLET_POOL_PATH", "./wallets.json")
    with open(wallet_path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Create Agent
# ---------------------------------------------------------------------------

async def create_agent(
    thesis: str,
    creator_name: str | None,
    db: Database,
    hedera_client: Any,
    custom_name: str | None = None,
    model: str | None = None,
) -> TradingAgent:
    """Create a brand-new trading agent end-to-end.

    1. LLM generates agent name + system prompt from the thesis.
    2. A Hedera wallet is assigned from the pool.
    3. The wallet is funded with 10,000 ARENA tokens.
    4. Agent row + initial portfolio are inserted into the DB.
    5. A :class:`TradingAgent` instance is returned.

    Parameters
    ----------
    thesis:
        Plain-English trading philosophy.
    creator_name:
        Who created this agent (user name or "System" for presets).
    db:
        Initialised :class:`Database` instance.
    hedera_client:
        :class:`HederaClient` instance (typed as ``Any`` to avoid circular imports).
    """
    # 1. LLM: thesis -> name + system_prompt
    generated = await thesis_to_prompt(thesis)
    name = custom_name.strip() if custom_name and custom_name.strip() else generated.name
    system_prompt = generated.system_prompt
    logger.info("Agent name=%r (custom=%s) for thesis=%r", name, bool(custom_name), thesis[:60])

    # 2. Assign wallet from pool
    wallet = hedera_client.assign_wallet()
    wallet_index: int = wallet["index"]
    account_id: str = wallet["account_id"]
    private_key: str = wallet["private_key"]
    logger.info("Assigned wallet index=%d account=%s", wallet_index, account_id)

    # 3. Fund with ARENA
    tx_id = await hedera_client.fund_agent(account_id, 10_000)
    logger.info("Funded agent account=%s tx=%s", account_id, tx_id)

    # 4. Generate unique ID
    agent_id = _make_agent_id(name)

    # 5. Persist agent row
    await db.execute(
        """
        INSERT INTO agents (id, name, thesis, system_prompt, creator_name,
                            is_preset, hedera_account_id, wallet_index)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            agent_id,
            name,
            thesis,
            system_prompt,
            creator_name or "",
            0,  # is_preset — caller can override via seed_presets
            account_id,
            wallet_index,
        ),
    )

    # 6. Init portfolio: 10,000 ARENA starting cash
    #    season_id 0 means "pre-season" — the orchestrator re-inits at season start
    await db.execute(
        """
        INSERT INTO portfolios (agent_id, season_id, asset, units, avg_entry_price)
        VALUES (?, 0, 'ARENA', 10000, 1.0)
        """,
        (agent_id,),
    )
    logger.info("Agent %s (%s) created and persisted", agent_id, name)

    # 7. Return instance
    return TradingAgent(
        id=agent_id,
        name=name,
        thesis=thesis,
        system_prompt=system_prompt,
        hedera_account_id=account_id,
        hedera_private_key=private_key,
        creator_name=creator_name or "",
        is_preset=False,
        temperature=0.7,
        wallet_index=wallet_index,
        model=model or "",
    )


# ---------------------------------------------------------------------------
# Load Agents
# ---------------------------------------------------------------------------

async def load_agents(db: Database) -> list[TradingAgent]:
    """Load all active agents from the database.

    Private keys are NOT stored in the DB for safety.  Instead, each agent's
    ``wallet_index`` is used to look up the key from the wallet pool file
    (``WALLET_POOL_PATH`` env var / ``wallets.json``).

    Returns a (possibly empty) list of :class:`TradingAgent` instances.
    """
    rows = await db.fetchall(
        "SELECT * FROM agents WHERE status = 'active' ORDER BY created_at"
    )
    if not rows:
        logger.info("No active agents found in DB")
        return []

    # Build index→private_key lookup from wallet pool
    wallet_pool = _load_wallet_pool()
    key_by_index: dict[int, str] = {
        w["index"]: w["private_key"] for w in wallet_pool
    }

    agents: list[TradingAgent] = []
    for row in rows:
        w_idx = row.get("wallet_index")
        private_key = key_by_index.get(w_idx, "") if w_idx is not None else ""
        if not private_key and w_idx is not None:
            logger.warning(
                "Agent %s has wallet_index=%d but no matching key in pool",
                row["id"], w_idx,
            )

        agents.append(
            TradingAgent(
                id=row["id"],
                name=row["name"],
                thesis=row["thesis"],
                system_prompt=row["system_prompt"],
                hedera_account_id=row.get("hedera_account_id", ""),
                hedera_private_key=private_key,
                creator_name=row.get("creator_name", ""),
                is_preset=bool(row.get("is_preset", 0)),
                temperature=0.7,
                wallet_index=w_idx if w_idx is not None else -1,
            )
        )

    logger.info("Loaded %d active agents from DB", len(agents))
    return agents


# ---------------------------------------------------------------------------
# Seed Presets
# ---------------------------------------------------------------------------

async def seed_presets(
    db: Database,
    hedera_client: Any,
) -> list[TradingAgent]:
    """Ensure the 4 preset agents exist — idempotent.

    For each preset in :data:`PRESET_THESES`, checks whether an agent with
    ``is_preset=1`` and matching thesis already exists.  If not, creates one
    via :func:`create_agent`.

    Returns the list of newly created agents (empty if all presets already existed).
    """
    created: list[TradingAgent] = []

    for key, preset in PRESET_THESES.items():
        thesis = preset["thesis"]
        creator_name = preset["creator_name"]

        # Check if this preset already exists
        existing = await db.fetchone(
            "SELECT id FROM agents WHERE is_preset = 1 AND thesis = ?",
            (thesis,),
        )
        if existing:
            logger.info("Preset %r already exists (id=%s), skipping", key, existing["id"])
            continue

        # Create the agent
        logger.info("Creating preset agent %r ...", key)
        agent = await create_agent(
            thesis=thesis,
            creator_name=creator_name,
            db=db,
            hedera_client=hedera_client,
        )

        # Mark as preset in DB (create_agent sets is_preset=0 by default)
        await db.execute(
            "UPDATE agents SET is_preset = 1 WHERE id = ?",
            (agent.id,),
        )
        agent.is_preset = True

        created.append(agent)
        logger.info("Preset %r created: %s (%s)", key, agent.id, agent.name)

    logger.info("seed_presets complete: %d new, %d already existed",
                len(created), len(PRESET_THESES) - len(created))
    return created


# ---------------------------------------------------------------------------
# Quick self-test (no real Hedera / LLM calls)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        print("=== Factory Demo (mock — no real LLM or Hedera) ===\n")

        # Show what _make_agent_id produces
        for sample_name in ["EthMaxi", "DOGE Lord", "Conservative Carl"]:
            aid = _make_agent_id(sample_name)
            print(f"  _make_agent_id({sample_name!r:25s}) -> {aid}")

        print("\nTo actually create agents, run seed_presets with a real DB + HederaClient.")
        print("Example:")
        print("  from engine.db.database import Database")
        print("  from engine.core.hedera_client import HederaClient")
        print("  db = Database(); await db.init()")
        print("  hc = HederaClient()")
        print("  agents = await seed_presets(db, hc)")

    asyncio.run(_demo())
