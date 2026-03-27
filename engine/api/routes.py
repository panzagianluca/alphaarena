"""REST API routes for Agent League.

All endpoints live under ``/api`` via an :class:`APIRouter`.
Shared state (db, orchestrator, hedera_client) is accessed through
``request.app.state``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from engine.agents.factory import create_agent, load_agents
from engine.agents.templates import PRESET_THESES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Agent Creation
# ---------------------------------------------------------------------------

@router.post("/agents/create")
async def create_agent_endpoint(request: Request):
    """Create a new trading agent from a plain-English thesis.

    Body: ``{ "thesis": str, "creator_name": str | null, "user_id": str | null,
              "instruments": list[str] | null, "model": str | null }``
    """
    body = await request.json()
    thesis: str = body.get("thesis", "")
    creator_name: str | None = body.get("creator_name")
    user_id: str | None = body.get("user_id")
    instruments: list[str] | None = body.get("instruments")
    model: str | None = body.get("model")
    agent_name: str | None = body.get("agent_name")

    if not thesis.strip():
        raise HTTPException(status_code=400, detail="thesis is required")

    db = request.app.state.db
    hedera = request.app.state.hedera_client

    # If user_id provided, verify user exists and has >= 1000 ARENA
    user = None
    if user_id:
        user = await db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        if not user:
            # User doesn't exist (stale localStorage) — proceed without deduction
            logger.warning("User %s not found in DB, skipping ARENA deduction", user_id)
            user_id = None
        elif user["arena_balance"] < 1000:
            raise HTTPException(
                status_code=400,
                detail="Insufficient balance: agent creation costs 1000 ARENA",
            )

    if instruments:
        logger.info("Agent creation requested instruments: %s", instruments)
    if model:
        logger.info("Agent creation requested model: %s", model)

    agent = await create_agent(
        thesis=thesis,
        creator_name=creator_name,
        db=db,
        hedera_client=hedera,
        custom_name=agent_name,
        model=model,
    )

    # Deduct 1000 ARENA from user after successful creation and record ownership
    if user_id:
        await db.execute(
            "UPDATE users SET arena_balance = arena_balance - 1000 WHERE id = ?",
            (user_id,),
        )
        await db.execute(
            "UPDATE agents SET user_id = ? WHERE id = ?",
            (user_id, agent.id),
        )

    # If a season is running, add the agent mid-season
    orchestrator = request.app.state.orchestrator
    if orchestrator and orchestrator.season_id is not None:
        await orchestrator.add_agent_mid_season(agent)

    return {
        "id": agent.id,
        "name": agent.name,
        "thesis": agent.thesis,
        "system_prompt": agent.system_prompt,
        "hedera_account_id": agent.hedera_account_id,
        "creator_name": agent.creator_name,
        "is_preset": agent.is_preset,
    }


@router.get("/agents/templates")
async def get_templates():
    """Return the 4 preset thesis templates."""
    return PRESET_THESES


# ---------------------------------------------------------------------------
# League
# ---------------------------------------------------------------------------

@router.get("/league")
async def get_league(request: Request):
    """Return current season status and leaderboard."""
    db = request.app.state.db

    season = await db.fetchone(
        "SELECT * FROM seasons ORDER BY id DESC LIMIT 1"
    )

    leaderboard = []
    if season:
        leaderboard = await db.fetchall(
            """
            SELECT l.*, a.name, a.thesis
            FROM leaderboard l
            JOIN agents a ON a.id = l.agent_id
            WHERE l.season_id = ?
            ORDER BY l.rank ASC
            """,
            (season["id"],),
        )

    return {
        "season": season,
        "leaderboard": leaderboard,
    }


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@router.get("/agents")
async def get_agents(request: Request):
    """Return all active agents with current leaderboard stats."""
    db = request.app.state.db

    agents = await db.fetchall(
        """
        SELECT a.*, l.total_pnl_usd, l.pnl_pct, l.sharpe_ratio,
               l.win_rate, l.max_drawdown_pct, l.total_trades, l.rank,
               COALESCE(alloc.total_backed, 0) as total_backed
        FROM agents a
        LEFT JOIN leaderboard l ON a.id = l.agent_id
            AND l.season_id = (SELECT MAX(id) FROM seasons)
        LEFT JOIN (
            SELECT agent_id, SUM(amount) as total_backed
            FROM allocations
            GROUP BY agent_id
        ) alloc ON a.id = alloc.agent_id
        WHERE a.status = 'active'
        ORDER BY COALESCE(l.rank, 999) ASC
        """
    )
    return agents


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    """Return agent profile + last 20 trades with reasoning."""
    db = request.app.state.db

    agent = await db.fetchone(
        """
        SELECT a.*, l.total_pnl_usd, l.pnl_pct, l.sharpe_ratio,
               l.win_rate, l.max_drawdown_pct, l.total_trades, l.rank
        FROM agents a
        LEFT JOIN leaderboard l ON a.id = l.agent_id
            AND l.season_id = (SELECT MAX(id) FROM seasons)
        WHERE a.id = ?
        """,
        (agent_id,),
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    trades = await db.fetchall(
        """
        SELECT * FROM trades
        WHERE agent_id = ?
        ORDER BY timestamp DESC
        LIMIT 50
        """,
        (agent_id,),
    )

    return {
        "agent": agent,
        "trades": trades,
    }


@router.get("/agents/{agent_id}/allocations")
async def get_agent_allocations(agent_id: str, request: Request):
    """Return all allocations (backers) for a specific agent."""
    db = request.app.state.db

    allocations = await db.fetchall(
        """
        SELECT al.amount, al.timestamp, al.hedera_tx_id, al.user_id,
               COALESCE(u.name, 'Anonymous') AS backer_name
        FROM allocations al
        LEFT JOIN users u ON al.user_id = u.id
        WHERE al.agent_id = ?
        ORDER BY al.timestamp DESC
        """,
        (agent_id,),
    )

    total_backed = sum(a["amount"] for a in allocations) if allocations else 0

    return {
        "allocations": allocations,
        "total_backed": total_backed,
    }


@router.get("/agents/{agent_id}/trades")
async def get_agent_trades(
    agent_id: str,
    request: Request,
    limit: int = 20,
    offset: int = 0,
):
    """Return paginated trades for a specific agent."""
    db = request.app.state.db

    # Verify agent exists
    agent = await db.fetchone(
        "SELECT id FROM agents WHERE id = ?", (agent_id,)
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    trades = await db.fetchall(
        """
        SELECT * FROM trades
        WHERE agent_id = ?
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        """,
        (agent_id, limit, offset),
    )
    return trades


# ---------------------------------------------------------------------------
# Season Control
# ---------------------------------------------------------------------------

@router.post("/season/start")
async def start_season(request: Request):
    """Start a new trading season."""
    orchestrator = request.app.state.orchestrator
    if orchestrator is None:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    if orchestrator.season_id is not None:
        raise HTTPException(status_code=409, detail="Season already active")

    season_info = await orchestrator.start_season()
    return season_info


@router.post("/season/tick")
async def tick_season(request: Request):
    """Manually trigger one round (demo control)."""
    orchestrator = request.app.state.orchestrator
    if orchestrator is None:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    if orchestrator.season_id is None:
        raise HTTPException(status_code=400, detail="No active season")

    if orchestrator.running:
        raise HTTPException(status_code=409, detail="Season loop is active — tick is only for manual mode")

    round_number = await orchestrator.tick()
    return {"round_number": round_number}


# ---------------------------------------------------------------------------
# Live Feed
# ---------------------------------------------------------------------------

@router.get("/feed")
async def get_feed(request: Request):
    """Return last 30 trades across all agents, ordered by most recent."""
    db = request.app.state.db

    trades = await db.fetchall(
        """
        SELECT t.*, a.name AS agent_name
        FROM trades t
        JOIN agents a ON a.id = t.agent_id
        ORDER BY t.timestamp DESC
        LIMIT 30
        """
    )
    return trades


# ---------------------------------------------------------------------------
# User Wallets
# ---------------------------------------------------------------------------

@router.post("/user/wallet")
async def create_user_wallet(request: Request):
    """Assign a wallet to a new user, fund with 50,000 ARENA."""
    db = request.app.state.db
    hedera = request.app.state.hedera_client

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    name = body.get("name", "Anonymous") or "Anonymous"

    wallet = hedera.assign_wallet()
    user_id = f"user-{wallet['index']:03d}"

    # Fund user with ARENA from treasury
    tx_id = await hedera.fund_agent(wallet["account_id"], 50_000)

    await db.execute(
        "INSERT OR IGNORE INTO users (id, name, hedera_account_id, wallet_index, arena_balance) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, wallet["account_id"], wallet["index"], 50000.0),
    )

    return {
        "user_id": user_id,
        "name": name,
        "hedera_account_id": wallet["account_id"],
        "arena_balance": 50000.0,
        "hedera_tx_id": tx_id,
    }


@router.get("/user/{user_id}/balance")
async def get_user_balance(user_id: str, request: Request):
    """Return user's ARENA balance and Hedera account."""
    db = request.app.state.db
    user = await db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": user["id"],
        "arena_balance": user["arena_balance"],
        "hedera_account_id": user["hedera_account_id"],
    }


# ---------------------------------------------------------------------------
# Capital Allocation
# ---------------------------------------------------------------------------

@router.post("/allocate")
async def allocate_capital(request: Request):
    """Allocate ARENA capital to an agent (real HTS transfer).

    Body: ``{ "agent_id": str, "amount": float, "user_id": str | null }``

    If ``user_id`` is provided, the transfer is user-funded:
    user balance is verified, a user-signed on-chain transfer is executed,
    and the user's arena_balance is deducted.  Otherwise, falls back to
    treasury-funded allocation (backward compatible).
    """
    body = await request.json()
    agent_id: str = body.get("agent_id", "")
    amount: float = body.get("amount", 0)
    user_id: str | None = body.get("user_id")

    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    db = request.app.state.db
    hedera = request.app.state.hedera_client

    # Look up agent's Hedera account
    agent = await db.fetchone(
        "SELECT hedera_account_id, wallet_index FROM agents WHERE id = ?", (agent_id,)
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_hedera_account_id = agent["hedera_account_id"]

    if user_id:
        # ---- User-funded allocation ----
        user = await db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["arena_balance"] < amount:
            raise HTTPException(
                status_code=400,
                detail="Insufficient ARENA balance",
            )

        # Look up user's private key from wallet pool via wallet_index
        user_private_key = hedera._wallet_pool[user["wallet_index"]]["private_key"]

        # Execute user-signed on-chain transfer
        tx_id = await hedera.transfer_user_to_agent(
            user_account_id=user["hedera_account_id"],
            user_private_key=user_private_key,
            agent_account_id=agent_hedera_account_id,
            amount=int(amount),
        )

        # Stub mode returns None — generate placeholder tx_id
        if tx_id is None:
            import time
            tx_id = f"stub-alloc-{int(time.time())}"

        # Deduct after transfer
        await db.execute(
            "UPDATE users SET arena_balance = arena_balance - ? WHERE id = ?",
            (amount, user_id),
        )
    else:
        # ---- Legacy treasury-funded allocation ----
        tx_id = await hedera.allocate_capital(agent_hedera_account_id, int(amount))
        if tx_id is None:
            import time
            tx_id = f"stub-alloc-{int(time.time())}"

    # Record the allocation
    if tx_id:
        season = await db.fetchone(
            "SELECT id FROM seasons ORDER BY id DESC LIMIT 1"
        )
        season_id = season["id"] if season else 0

        await db.execute(
            """
            INSERT INTO allocations (agent_id, season_id, amount, user_id, hedera_tx_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, season_id, amount, user_id, tx_id),
        )

    return {
        "agent_id": agent_id,
        "amount": amount,
        "hedera_tx_id": tx_id,
    }


@router.get("/portfolio-history")
async def get_portfolio_history(request: Request):
    """Return portfolio value snapshots per agent per round for charting.

    Builds history from trades table: for each round, compute each agent's
    portfolio_value_after. Returns array of {round, AgentName: value, ...}.
    """
    db = request.app.state.db

    # Get latest season
    season = await db.fetchone(
        "SELECT id FROM seasons ORDER BY id DESC LIMIT 1"
    )
    if not season:
        return []

    season_id = season["id"]

    # Get all agents
    agents = await db.fetchall(
        "SELECT id, name FROM agents WHERE status = 'active'"
    )
    agent_names = {a["id"]: a["name"] for a in agents}

    # Get last trade per agent per round (portfolio_value_after)
    trades = await db.fetchall(
        """
        SELECT agent_id, round_number, portfolio_value_after
        FROM trades
        WHERE season_id = ?
        ORDER BY round_number ASC, id ASC
        """,
        (season_id,),
    )

    # Build latest value per agent, forward-filling
    # Group trades into time-based snapshots (every ~30s scoring update)
    last_known: dict[str, float] = {name: 10000.0 for name in agent_names.values()}
    snapshots_by_round: dict[int, dict[str, float]] = {}

    for t in trades:
        agent_name = agent_names.get(t["agent_id"], t["agent_id"])
        val = t["portfolio_value_after"]
        if val is not None:
            last_known[agent_name] = val

        rn = t["round_number"]
        if rn not in snapshots_by_round:
            # Snapshot all agents at this point (forward-fill)
            snapshots_by_round[rn] = dict(last_known)
        else:
            snapshots_by_round[rn][agent_name] = val if val is not None else last_known[agent_name]

    # Thin to max ~60 data points for chart performance
    all_rounds = sorted(snapshots_by_round.keys())
    if len(all_rounds) > 60:
        step = len(all_rounds) // 60
        all_rounds = all_rounds[::step] + [all_rounds[-1]]

    result = []
    chart_round = 1
    for rn in all_rounds:
        snapshot = {"round": chart_round}
        snapshot.update(snapshots_by_round[rn])
        result.append(snapshot)
        chart_round += 1

    return result


# ---------------------------------------------------------------------------
# Faucet
# ---------------------------------------------------------------------------

@router.post("/user/{user_id}/faucet")
async def faucet(user_id: str, request: Request):
    """Give the user 10,000 more ARENA from treasury (max 3 claims)."""
    db = request.app.state.db
    hedera = request.app.state.hedera_client

    user = await db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user["faucet_claims"] >= 3:
        raise HTTPException(
            status_code=429,
            detail="Faucet limit reached: max 3 claims per user",
        )

    tx_id = await hedera.fund_agent(user["hedera_account_id"], 10_000)

    await db.execute(
        """
        UPDATE users
        SET arena_balance = arena_balance + 10000,
            faucet_claims = faucet_claims + 1
        WHERE id = ?
        """,
        (user_id,),
    )

    updated = await db.fetchone(
        "SELECT arena_balance FROM users WHERE id = ?", (user_id,)
    )

    return {
        "arena_balance": updated["arena_balance"],
        "hedera_tx_id": tx_id,
    }


# ---------------------------------------------------------------------------
# User Portfolio
# ---------------------------------------------------------------------------

@router.get("/user/{user_id}/portfolio")
async def get_user_portfolio(user_id: str, request: Request):
    """Return the user's full portfolio view: balance, agents created, allocations."""
    db = request.app.state.db

    user = await db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    agents_created = await db.fetchall(
        """
        SELECT a.*, l.pnl_pct, l.rank, l.total_trades
        FROM agents a
        LEFT JOIN leaderboard l ON a.id = l.agent_id
            AND l.season_id = (SELECT MAX(id) FROM seasons)
        WHERE a.user_id = ?
        """,
        (user_id,),
    )

    allocations = await db.fetchall(
        """
        SELECT al.*, a.name AS agent_name
        FROM allocations al
        JOIN agents a ON al.agent_id = a.id
        WHERE al.user_id = ?
        ORDER BY al.timestamp DESC
        """,
        (user_id,),
    )

    return {
        "balance": user["arena_balance"],
        "agents_created": agents_created,
        "allocations": allocations,
    }


# ---------------------------------------------------------------------------
# Tips
# ---------------------------------------------------------------------------

@router.get("/tips")
async def get_tips(request: Request):
    """Return recent agent-to-agent tips with agent names."""
    db = request.app.state.db

    tips = await db.fetchall(
        """
        SELECT t.*, fa.name AS from_agent_name, ta.name AS to_agent_name
        FROM tips t
        JOIN agents fa ON fa.id = t.from_agent_id
        JOIN agents ta ON ta.id = t.to_agent_id
        ORDER BY t.timestamp DESC
        LIMIT 50
        """
    )
    return tips


# ---------------------------------------------------------------------------
# Withdrawals
# ---------------------------------------------------------------------------

@router.post("/withdraw")
async def withdraw(request: Request):
    """Withdraw returns from an agent allocation.

    Body: ``{ "user_id": str, "agent_id": str }``

    Calculates proportional returns based on agent P&L, transfers from
    treasury to user wallet, updates user balance, and marks the
    allocation as withdrawn.
    """
    body = await request.json()
    user_id: str = body.get("user_id", "")
    agent_id: str = body.get("agent_id", "")

    if not user_id or not agent_id:
        raise HTTPException(status_code=400, detail="user_id and agent_id are required")

    db = request.app.state.db
    hedera = request.app.state.hedera_client

    # Verify user exists
    user = await db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find non-withdrawn allocation for this user+agent
    allocation = await db.fetchone(
        """
        SELECT al.*, l.pnl_pct
        FROM allocations al
        LEFT JOIN leaderboard l ON l.agent_id = al.agent_id
            AND l.season_id = al.season_id
        WHERE al.user_id = ? AND al.agent_id = ? AND al.withdrawn = 0
        ORDER BY al.timestamp DESC
        LIMIT 1
        """,
        (user_id, agent_id),
    )
    if not allocation:
        raise HTTPException(
            status_code=404,
            detail="No active allocation found for this user and agent",
        )

    # Check if already withdrawn
    if allocation["withdrawn"] == 1:
        raise HTTPException(status_code=400, detail="Allocation already withdrawn")

    # Calculate returns
    original_amount = allocation["amount"]
    pnl_pct = allocation["pnl_pct"] or 0.0
    return_amount = round(original_amount * (1 + pnl_pct / 100), 2)
    profit = round(return_amount - original_amount, 2)

    # Transfer from treasury to user wallet
    try:
        tx_id = await hedera.fund_agent(user["hedera_account_id"], int(return_amount))
    except Exception:
        logger.exception("Withdrawal transfer failed for user %s", user_id)
        tx_id = None

    # Update user balance
    await db.execute(
        "UPDATE users SET arena_balance = arena_balance + ? WHERE id = ?",
        (return_amount, user_id),
    )

    # Mark allocation as withdrawn
    await db.execute(
        "UPDATE allocations SET withdrawn = 1 WHERE id = ?",
        (allocation["id"],),
    )

    # Broadcast withdrawal event
    orchestrator = request.app.state.orchestrator
    if orchestrator and orchestrator.broadcast_callback:
        try:
            await orchestrator.broadcast_callback({
                "type": "withdrawal",
                "data": {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "original_amount": original_amount,
                    "return_amount": return_amount,
                    "profit": profit,
                    "hedera_tx_id": tx_id,
                },
            })
        except Exception:
            logger.exception("Withdrawal broadcast failed (non-fatal)")

    return {
        "original_amount": original_amount,
        "return_amount": return_amount,
        "profit": profit,
        "hedera_tx_id": tx_id,
    }


@router.get("/user/{user_id}/withdrawable")
async def get_withdrawable(user_id: str, request: Request):
    """Return list of non-withdrawn allocations with current value based on agent P&L.

    Each entry includes original_amount, current_value, and profit/loss.
    """
    db = request.app.state.db

    # Verify user exists
    user = await db.fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    allocations = await db.fetchall(
        """
        SELECT al.id, al.agent_id, al.amount, al.season_id, al.timestamp,
               al.hedera_tx_id, a.name AS agent_name,
               COALESCE(l.pnl_pct, 0) AS pnl_pct
        FROM allocations al
        JOIN agents a ON a.id = al.agent_id
        LEFT JOIN leaderboard l ON l.agent_id = al.agent_id
            AND l.season_id = al.season_id
        WHERE al.user_id = ? AND al.withdrawn = 0
        ORDER BY al.timestamp DESC
        """,
        (user_id,),
    )

    result = []
    for alloc in allocations:
        original = alloc["amount"]
        pnl_pct = alloc["pnl_pct"]
        current_value = round(original * (1 + pnl_pct / 100), 2)
        profit = round(current_value - original, 2)
        result.append({
            "allocation_id": alloc["id"],
            "agent_id": alloc["agent_id"],
            "agent_name": alloc["agent_name"],
            "original_amount": original,
            "current_value": current_value,
            "profit": profit,
            "pnl_pct": pnl_pct,
            "timestamp": alloc["timestamp"],
        })

    return result
