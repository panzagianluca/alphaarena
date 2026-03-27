"""Orchestrator -- the brain that runs the Agent League trading game loop.

Ties together all subsystems:
  - MarketFeed   (price data)
  - PortfolioManager (in-memory + DB portfolio tracking)
  - HederaClient (on-chain HTS transfers + HCS publishing)
  - TradingAgent (LLM-driven trade decisions)
  - Scoring      (leaderboard computation)
  - Database     (persistence)

One round:
  1. Fetch prices
  2. Publish prices to HCS
  3. Build RoundContext per agent
  4. All agents decide in parallel (LLM calls)
  5. Execute trades sequentially (portfolio + Hedera + DB)
  6. Score + rank + update leaderboard
  7. Broadcast to WebSocket clients
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from engine.agents.base import TradingAgent
from engine.agents.factory import load_agents
from engine.agents.schemas import RoundContext, TradeDecision
from engine.core.llm import generate_commentary
from engine.core.scoring import calculate_scores, rank_agents
from engine.db.database import Database

logger = logging.getLogger(__name__)


class Orchestrator:
    """Runs the trading game loop -- one season at a time."""

    def __init__(
        self,
        db: Database,
        hedera: Any,       # HederaClient (Any to avoid import-time env var failures)
        market: Any,        # MarketFeed
        portfolio: Any,     # PortfolioManager
    ) -> None:
        self.db = db
        self.hedera = hedera
        self.market = market
        self.portfolio = portfolio

        self.agents: list[TradingAgent] = []
        self.season_id: int | None = None
        self.round_number: int = 0
        self.total_rounds: int = 0  # 0 = continuous (no limit)
        self.running: bool = False
        self._trade_count: int = 0  # global trade counter

        # Set by FastAPI to push data to WebSocket clients.
        self.broadcast_callback: Callable[..., Coroutine] | None = None

        # Per-agent background tasks
        self._agent_tasks: dict[str, asyncio.Task] = {}
        # Scoring task
        self._scoring_task: asyncio.Task | None = None
        # Lock for portfolio/DB writes
        self._trade_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Broadcast helper
    # ------------------------------------------------------------------

    def set_broadcast_callback(self, callback: Callable[..., Coroutine]) -> None:
        """Store the async broadcast callback (called by FastAPI on startup)."""
        self.broadcast_callback = callback

    async def _broadcast(self, data: dict[str, Any]) -> None:
        """Send *data* to all connected WebSocket clients (if callback is set)."""
        if self.broadcast_callback is not None:
            try:
                await self.broadcast_callback(data)
            except Exception:
                logger.exception("Broadcast callback failed")

    # ------------------------------------------------------------------
    # Season lifecycle
    # ------------------------------------------------------------------

    async def start_season(
        self,
        total_rounds: int = 0,
        interval_sec: int = 30,
    ) -> int:
        """Start a new season with per-agent async loops.

        Each agent runs independently on its own timer (20-45s random cooldown).
        A separate scoring loop updates the leaderboard every 30s.

        total_rounds=0 means continuous (no round limit).
        Returns the new season_id.
        """
        import random as _random
        self.total_rounds = total_rounds

        # 1. Load active agents -------------------------------------------
        self.agents = await load_agents(self.db)
        if not self.agents:
            logger.warning("No active agents found -- season will be empty")

        # 2. Create season row --------------------------------------------
        await self.db.execute(
            """
            INSERT INTO seasons (status, total_rounds, round_interval_sec, started_at)
            VALUES ('active', ?, ?, ?)
            """,
            (total_rounds, interval_sec, datetime.now(timezone.utc).isoformat()),
        )
        row = await self.db.fetchone(
            "SELECT id FROM seasons ORDER BY id DESC LIMIT 1"
        )
        assert row is not None, "Failed to create season row"
        self.season_id = row["id"]
        self.round_number = 0
        self._trade_count = 0
        self.running = True

        logger.info(
            "Season %d started: %d agents, continuous mode, ~%ds agent cooldown",
            self.season_id, len(self.agents), interval_sec,
        )

        # 3. Init portfolios for each agent --------------------------------
        for agent in self.agents:
            await self.portfolio.init_agent(
                agent_id=agent.id,
                season_id=self.season_id,
                starting_cash=10_000.0,
            )

        # 4. Start Binance WS if market supports it ------------------------
        if hasattr(self.market, 'start_ws'):
            await self.market.start_ws()

        # 5. Launch per-agent trading loops ---------------------------------
        for agent in self.agents:
            cooldown = _random.randint(20, 45)
            task = asyncio.create_task(
                self._agent_loop(agent, cooldown),
                name=f"agent-{agent.id}",
            )
            self._agent_tasks[agent.id] = task

        # 6. Launch scoring/broadcast loop ---------------------------------
        self._scoring_task = asyncio.create_task(
            self._scoring_loop(interval_sec=30),
            name=f"season-{self.season_id}-scoring",
        )

        return self.season_id

    # ------------------------------------------------------------------
    # LEGACY: run_round kept as stub for backward compat with tick()
    # ------------------------------------------------------------------

    async def run_round(self) -> None:
        """Legacy stub — the real logic is in _agent_loop + _scoring_loop."""
        pass

    async def tick(self) -> int:
        """Manual tick — triggers a scoring update in event-driven mode."""
        self.round_number += 1
        return self.round_number

    # ------------------------------------------------------------------
    # Per-agent trading loop (event-driven)
    # ------------------------------------------------------------------

    async def _agent_loop(self, agent: TradingAgent, cooldown_sec: int = 30) -> None:
        """Independent trading loop for a single agent.

        Each agent checks prices, decides, and trades on its own timer.
        Trades trickle in continuously — no batching.
        """
        import random as _random

        # Small random initial delay so agents don't all start at once
        await asyncio.sleep(_random.uniform(1, 5))

        while self.running:
            try:
                # 1. Get latest prices (instant from WS cache)
                prices = await self.market.fetch()
                if not prices:
                    await asyncio.sleep(5)
                    continue

                # 2. Build context for this agent
                portfolio_snap = self.portfolio.get_portfolio(agent.id, prices)
                recent_trades = await self.db.fetchall(
                    "SELECT * FROM trades WHERE agent_id = ? AND season_id = ? "
                    "ORDER BY round_number DESC LIMIT 5",
                    (agent.id, self.season_id),
                )
                league_standings = await self.db.fetchall(
                    "SELECT * FROM leaderboard WHERE season_id = ? ORDER BY rank ASC",
                    (self.season_id,),
                )

                self._trade_count += 1
                trade_number = self._trade_count

                ctx = RoundContext(
                    round_number=trade_number,
                    total_rounds=self.total_rounds or 9999,
                    market={k: v for k, v in prices.items()},
                    portfolio=portfolio_snap,
                    recent_trades=recent_trades,
                    league_standings=league_standings,
                )

                # 3. Agent decides (LLM call)
                try:
                    decision = await agent.decide(ctx)
                except Exception:
                    logger.exception("Agent %s decision failed", agent.id)
                    decision = TradeDecision(action="hold", asset="NONE", amount_pct=0, reasoning="Decision error — holding", confidence=0)

                # 4. Execute trade (with lock for portfolio consistency)
                trade_record = await self._execute_single_trade(agent, decision, prices, trade_number)

                # 5. Broadcast the trade to all connected clients
                if trade_record:
                    await self._broadcast({
                        "type": "trades",
                        "data": [trade_record],
                    })

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Agent %s loop error (non-fatal)", agent.id)

            # Cooldown with jitter
            jitter = _random.uniform(-5, 5)
            await asyncio.sleep(max(10, cooldown_sec + jitter))

    async def _execute_single_trade(
        self, agent: TradingAgent, decision: TradeDecision, prices: dict, trade_number: int
    ) -> dict | None:
        """Execute one trade for one agent. Returns the trade record dict."""
        action = decision.action
        asset = decision.asset if decision.asset != "NONE" else None

        async with self._trade_lock:
            # Validate
            if action != "hold" and asset:
                if not self.portfolio.can_execute(agent.id, action, asset, decision.amount_pct, prices):
                    action = "hold"
                    asset = None

            # Execute portfolio update
            trade_result = self.portfolio.execute_trade(
                agent.id, action, asset or "", decision.amount_pct, prices
            )

            # Execute on Hedera
            hedera_tx_id = None
            if action != "hold" and asset:
                try:
                    hedera_tx_id = await self.hedera.execute_trade(
                        action=action,
                        asset=asset,
                        amount_tokens=trade_result["amount_tokens"],
                        agent_account_id=agent.hedera_account_id,
                        agent_private_key=agent.hedera_private_key,
                    )
                except Exception:
                    logger.exception("Hedera trade failed for %s (non-fatal)", agent.id)

            # Publish reasoning to HCS
            hcs_tx_id = None
            try:
                hcs_tx_id = await self.hedera.publish_trade_reasoning(
                    agent_name=agent.name,
                    round_number=trade_number,
                    decision=decision,
                    hedera_tx_id=hedera_tx_id,
                )
            except Exception:
                logger.debug("HCS publish failed for %s (non-fatal)", agent.id)

            # Persist to DB
            trade_record = {
                "season_id": self.season_id,
                "agent_id": agent.id,
                "round_number": trade_number,
                "action": action,
                "asset": asset,
                "amount_pct": decision.amount_pct if action != "hold" else 0,
                "amount_tokens": trade_result["amount_tokens"],
                "price_at_trade": prices.get(asset, {}).get("price_usd", 0) if asset else 0,
                "reasoning": decision.reasoning,
                "confidence": decision.confidence,
                "mood": decision.mood,
                "hedera_tx_id": hedera_tx_id,
                "hcs_tx_id": hcs_tx_id,
                "portfolio_value_after": trade_result["portfolio_value_after"],
                "agent_name": agent.name,
            }

            await self.db.execute(
                """
                INSERT INTO trades (season_id, agent_id, round_number, action, asset,
                    amount_pct, amount_tokens, price_at_trade, reasoning, confidence, mood,
                    hedera_tx_id, hcs_tx_id, portfolio_value_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.season_id, agent.id, trade_number, action, asset,
                    trade_record["amount_pct"], trade_result["amount_tokens"],
                    trade_record["price_at_trade"], decision.reasoning,
                    decision.confidence, decision.mood,
                    hedera_tx_id, hcs_tx_id, trade_result["portfolio_value_after"],
                ),
            )

            # Persist portfolio
            await self.portfolio.persist(agent.id, self.season_id)

        return trade_record

    # ------------------------------------------------------------------
    # Agent-to-Agent Tips
    # ------------------------------------------------------------------

    async def _distribute_tips(self) -> None:
        """Top-ranked agent tips 2nd (50 aUSD) and 3rd (25 aUSD) place agents.

        Demonstrates agent-to-agent payment flows on Hedera. Called after
        each scoring update. Gracefully handles fewer than 3 agents.
        """
        if self.season_id is None:
            return

        # Fetch current leaderboard ranked by position
        ranked = await self.db.fetchall(
            """
            SELECT l.agent_id, l.rank, a.hedera_account_id, a.name
            FROM leaderboard l
            JOIN agents a ON a.id = l.agent_id
            WHERE l.season_id = ?
            ORDER BY l.rank ASC
            """,
            (self.season_id,),
        )

        if len(ranked) < 2:
            return

        top_agent = ranked[0]
        tip_targets = [
            (ranked[1], 50),   # 2nd place gets 50 aUSD
        ]
        if len(ranked) >= 3:
            tip_targets.append((ranked[2], 25))  # 3rd place gets 25 aUSD

        tip_records = []
        for target, amount in tip_targets:
            # Execute Hedera transfer (treasury-funded, simulating agent tip)
            try:
                tx_id = await self.hedera.fund_agent(
                    target["hedera_account_id"], amount,
                )
            except Exception:
                logger.exception(
                    "Tip transfer failed: %s -> %s (%d aUSD)",
                    top_agent["agent_id"], target["agent_id"], amount,
                )
                tx_id = None

            # Record in DB
            await self.db.execute(
                """
                INSERT INTO tips (from_agent_id, to_agent_id, amount, season_id, hedera_tx_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (top_agent["agent_id"], target["agent_id"], amount, self.season_id, tx_id),
            )

            tip_records.append({
                "from_agent_id": top_agent["agent_id"],
                "from_agent_name": top_agent["name"],
                "to_agent_id": target["agent_id"],
                "to_agent_name": target["name"],
                "amount": amount,
                "hedera_tx_id": tx_id,
            })

        # Broadcast all tips in one message
        if tip_records:
            await self._broadcast({
                "type": "tips",
                "data": tip_records,
            })

        logger.info(
            "Distributed %d tip(s) from %s (rank 1)",
            len(tip_records), top_agent["name"],
        )

    # ------------------------------------------------------------------
    # Scoring loop (runs independently, updates leaderboard every 30s)
    # ------------------------------------------------------------------

    async def _scoring_loop(self, interval_sec: int = 30) -> None:
        """Periodically recalculate scores and broadcast leaderboard."""
        while self.running:
            await asyncio.sleep(interval_sec)
            if not self.running:
                break

            try:
                self.round_number += 1
                prices = await self.market.fetch()
                if not prices:
                    continue

                # Calculate scores for all agents
                all_scores: dict[str, dict] = {}
                portfolio_snapshots: dict[str, float] = {}

                for agent in self.agents:
                    total_val = self.portfolio.get_total_value(agent.id, prices)
                    portfolio_snapshots[agent.name] = round(total_val, 2)

                    agent_trades = await self.db.fetchall(
                        "SELECT * FROM trades WHERE agent_id = ? AND season_id = ? ORDER BY round_number ASC",
                        (agent.id, self.season_id),
                    )
                    scores = calculate_scores(agent_trades, total_val)
                    all_scores[agent.id] = scores

                ranked = rank_agents(all_scores)

                # Update leaderboard DB
                for entry in ranked:
                    agent_id = entry["agent_id"]
                    await self.db.execute(
                        """
                        INSERT OR REPLACE INTO leaderboard
                        (agent_id, season_id, total_pnl_usd, pnl_pct, sharpe_ratio,
                         win_rate, max_drawdown_pct, total_trades, rank)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            agent_id, self.season_id,
                            entry.get("pnl_usd", 0), entry.get("pnl_pct", 0),
                            entry.get("sharpe_ratio", 0), entry.get("win_rate", 0),
                            entry.get("max_drawdown_pct", 0), entry.get("total_trades", 0),
                            entry.get("rank", 999),
                        ),
                    )

                # Update season rounds_completed
                await self.db.execute(
                    "UPDATE seasons SET rounds_completed = ? WHERE id = ?",
                    (self.round_number, self.season_id),
                )

                # Broadcast leaderboard
                leaderboard_broadcast = []
                for entry in ranked:
                    agent_id = entry["agent_id"]
                    agent_obj = next((a for a in self.agents if a.id == agent_id), None)
                    leaderboard_broadcast.append({
                        "agent_id": agent_id,
                        "name": agent_obj.name if agent_obj else agent_id,
                        "pnl_pct": entry.get("pnl_pct", 0),
                        "total_trades": entry.get("total_trades", 0),
                        "sharpe_ratio": entry.get("sharpe_ratio", 0),
                        "win_rate": entry.get("win_rate", 0),
                        "max_drawdown_pct": entry.get("max_drawdown_pct", 0),
                        "rank": entry.get("rank", 999),
                    })

                await self._broadcast({
                    "type": "leaderboard",
                    "data": leaderboard_broadcast,
                })

                # Broadcast portfolio snapshots for chart
                portfolio_snapshots["round"] = self.round_number
                await self._broadcast({
                    "type": "round_complete",
                    "data": {
                        "round": self.round_number,
                        "portfolios": portfolio_snapshots,
                    },
                })

                # Distribute tips from top agent to 2nd/3rd
                try:
                    await self._distribute_tips()
                except Exception:
                    logger.exception("Tip distribution failed (non-fatal)")

                logger.info(
                    "Scoring update #%d: %d agents scored",
                    self.round_number, len(all_scores),
                )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scoring loop error (non-fatal)")

    # ------------------------------------------------------------------
    # Mid-season agent addition
    # ------------------------------------------------------------------

    async def add_agent_mid_season(self, agent: TradingAgent) -> None:
        """Add a newly created agent to the running season.

        Spawns a new per-agent trading loop immediately.
        """
        import random as _random

        if self.season_id is None:
            raise RuntimeError("No active season")

        self.agents.append(agent)

        await self.portfolio.init_agent(
            agent_id=agent.id,
            season_id=self.season_id,
            starting_cash=10_000.0,
        )

        logger.info(
            "Agent %s (%s) added mid-season %d (will trade from round %d)",
            agent.id, agent.name, self.season_id, self.round_number + 1,
        )

        await self._broadcast({
            "type": "new_agent",
            "data": {
                "id": agent.id,
                "name": agent.name,
                "thesis": agent.thesis,
                "hedera_account_id": agent.hedera_account_id,
            },
        })

        # Spawn a per-agent trading loop
        cooldown = _random.randint(20, 45)
        task = asyncio.create_task(
            self._agent_loop(agent, cooldown),
            name=f"agent-{agent.id}",
        )
        self._agent_tasks[agent.id] = task

    # ------------------------------------------------------------------
    # Finish season — cancel all agent tasks
    # ------------------------------------------------------------------

    async def _finish_season(self) -> None:
        """Mark the season as completed and clean up all agent tasks."""
        self.running = False

        # Cancel all agent loops
        for task in self._agent_tasks.values():
            task.cancel()
        if self._scoring_task:
            self._scoring_task.cancel()
        self._agent_tasks.clear()
        self._scoring_task = None

        if self.season_id is None:
            return

        winner_row = await self.db.fetchone(
            "SELECT agent_id FROM leaderboard WHERE season_id = ? ORDER BY rank ASC LIMIT 1",
            (self.season_id,),
        )
        winner_id = winner_row["agent_id"] if winner_row else None

        await self.db.execute(
            "UPDATE seasons SET status = 'completed', ended_at = ?, winner_agent_id = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), winner_id, self.season_id),
        )

        logger.info("Season %d completed. Winner: %s", self.season_id, winner_id)

        await self._broadcast({
            "type": "season_end",
            "data": {
                "season_id": self.season_id,
                "winner_agent_id": winner_id,
            },
        })

        self.season_id = None
        self.round_number = 0
        self.total_rounds = 0


# ---------------------------------------------------------------------------
# Quick self-test: instantiate with mock dependencies
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio as _asyncio

    class _MockDB:
        async def execute(self, sql, params=()):
            pass

        async def fetchone(self, sql, params=()):
            if "seasons" in sql:
                return {"id": 1}
            return None

        async def fetchall(self, sql, params=()):
            return []

    class _MockHedera:
        async def publish_prices(self, prices, round_number):
            return None

        async def execute_trade(self, **kw):
            return None

        async def publish_trade_reasoning(self, **kw):
            return None

    class _MockMarket:
        async def fetch(self):
            return {
                "BTC": {"price_usd": 98000, "change_1h_pct": 0.5, "change_24h_pct": 1.2, "volume_trend": "stable"},
                "ETH": {"price_usd": 3800, "change_1h_pct": -0.3, "change_24h_pct": 0.8, "volume_trend": "stable"},
                "HBAR": {"price_usd": 0.28, "change_1h_pct": 0.1, "change_24h_pct": -0.5, "volume_trend": "stable"},
                "DOGE": {"price_usd": 0.18, "change_1h_pct": 1.0, "change_24h_pct": 3.5, "volume_trend": "surging"},
            }

    class _MockPortfolio:
        def __init__(self):
            self._data = {}

        async def init_agent(self, agent_id, season_id, starting_cash=10000):
            self._data[agent_id] = starting_cash

        def get_portfolio(self, agent_id, prices):
            return {"cash": self._data.get(agent_id, 0), "positions": [], "total_value": self._data.get(agent_id, 0), "total_pnl_pct": 0}

        def can_execute(self, agent_id, action, asset, amount_pct, prices):
            return True

        def execute_trade(self, agent_id, action, asset, amount_pct, prices):
            return {"amount_tokens": 0, "price": 0, "portfolio_value_after": 10000, "realized_pnl": 0}

        def get_total_value(self, agent_id, prices):
            return self._data.get(agent_id, 0)

        async def persist(self, agent_id, season_id):
            pass

    async def _main():
        orch = Orchestrator(
            db=_MockDB(),
            hedera=_MockHedera(),
            market=_MockMarket(),
            portfolio=_MockPortfolio(),
        )
        print(f"Orchestrator created:  season_id={orch.season_id}, round={orch.round_number}")
        print(f"  agents:  {len(orch.agents)}")
        print(f"  running: {orch.running}")
        print(f"  broadcast_callback: {orch.broadcast_callback}")
        print()
        print("Orchestrator is ready to start_season().")
        print("(Not starting -- would require active agents in DB + LLM keys)")

    _asyncio.run(_main())
