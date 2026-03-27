"""
Portfolio manager for Agent League.

Tracks each agent's holdings in memory (dict) and persists to the DB.
Portfolios operate in "ARENA units" mapped to USD via prices.
10,000 ARENA = $10,000 starting capital.
"""

from __future__ import annotations

from typing import Any

from engine.db.database import Database

DEFAULT_STARTING_CASH = 10_000.0


class PortfolioManager:
    """In-memory portfolio state with DB persistence."""

    def __init__(self, db: Database) -> None:
        self.db = db
        # Per-agent state: { agent_id: {"cash": float, "positions": {asset: {"units": float, "avg_entry_price": float}}} }
        self._portfolios: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def init_agent(
        self,
        agent_id: str,
        season_id: int,
        starting_cash: float = DEFAULT_STARTING_CASH,
    ) -> None:
        """Set up a fresh portfolio for *agent_id* with the given starting cash."""
        self._portfolios[agent_id] = {
            "cash": starting_cash,
            "positions": {},
        }
        # Persist the initial ARENA (cash) row.
        await self.db.execute(
            """
            INSERT OR REPLACE INTO portfolios (agent_id, season_id, asset, units, avg_entry_price)
            VALUES (?, ?, 'ARENA', ?, 1.0)
            """,
            (agent_id, season_id, starting_cash),
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_portfolio(self, agent_id: str, prices: dict) -> dict:
        """Return a snapshot of the agent's portfolio at current market prices.

        Returns
        -------
        dict with keys:
            cash, positions (list of dicts), total_value, total_pnl_pct
        """
        state = self._portfolios.get(agent_id)
        if state is None:
            return {
                "cash": 0,
                "positions": [],
                "total_value": 0,
                "total_pnl_pct": 0,
            }

        cash = state["cash"]
        positions_list: list[dict] = []
        positions_value = 0.0

        for asset, pos in state["positions"].items():
            units = pos["units"]
            avg_entry = pos["avg_entry_price"]
            current_price = prices.get(asset, {}).get("price_usd", avg_entry)
            current_value = units * current_price
            unrealized_pnl_pct = (
                ((current_price - avg_entry) / avg_entry * 100) if avg_entry > 0 else 0.0
            )
            positions_list.append(
                {
                    "asset": asset,
                    "units": units,
                    "avg_entry_price": avg_entry,
                    "current_value": current_value,
                    "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                }
            )
            positions_value += current_value

        total_value = cash + positions_value
        total_pnl_pct = (total_value - DEFAULT_STARTING_CASH) / DEFAULT_STARTING_CASH * 100

        return {
            "cash": round(cash, 2),
            "positions": positions_list,
            "total_value": round(total_value, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
        }

    def get_total_value(self, agent_id: str, prices: dict) -> float:
        """Quick helper: cash + sum of position values at current prices."""
        state = self._portfolios.get(agent_id)
        if state is None:
            return 0.0
        total = state["cash"]
        for asset, pos in state["positions"].items():
            price = prices.get(asset, {}).get("price_usd", pos["avg_entry_price"])
            total += pos["units"] * price
        return total

    # ------------------------------------------------------------------
    # Trade validation
    # ------------------------------------------------------------------

    def can_execute(
        self,
        agent_id: str,
        action: str,
        asset: str,
        amount_pct: float,
        prices: dict,
    ) -> bool:
        """Check whether the agent can perform the requested trade."""
        if action == "hold":
            return True

        state = self._portfolios.get(agent_id)
        if state is None:
            return False

        if action == "buy":
            # Must have some cash and a valid percentage.
            return state["cash"] > 0 and amount_pct > 0

        if action == "sell":
            pos = state["positions"].get(asset)
            return pos is not None and pos["units"] > 0

        return False

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def execute_trade(
        self,
        agent_id: str,
        action: str,
        asset: str,
        amount_pct: float,
        prices: dict,
    ) -> dict:
        """Execute a trade and update the in-memory portfolio.

        Returns
        -------
        dict with keys:
            amount_tokens, price, portfolio_value_after, realized_pnl
        """
        state = self._portfolios[agent_id]
        realized_pnl = 0.0
        amount_tokens = 0.0
        price = prices.get(asset, {}).get("price_usd", 0.0)

        if action == "buy":
            cash_to_spend = state["cash"] * (amount_pct / 100.0)
            units_bought = cash_to_spend / price if price > 0 else 0.0

            state["cash"] -= cash_to_spend

            pos = state["positions"].get(asset)
            if pos is None:
                state["positions"][asset] = {
                    "units": units_bought,
                    "avg_entry_price": price,
                }
            else:
                # Weighted average entry price.
                old_cost = pos["units"] * pos["avg_entry_price"]
                new_cost = units_bought * price
                total_units = pos["units"] + units_bought
                pos["avg_entry_price"] = (
                    (old_cost + new_cost) / total_units if total_units > 0 else price
                )
                pos["units"] = total_units

            amount_tokens = units_bought

        elif action == "sell":
            pos = state["positions"][asset]
            units_to_sell = pos["units"] * (amount_pct / 100.0)
            cash_received = units_to_sell * price

            realized_pnl = (price - pos["avg_entry_price"]) * units_to_sell

            pos["units"] -= units_to_sell
            state["cash"] += cash_received

            # Clean up empty positions.
            if pos["units"] <= 1e-12:
                del state["positions"][asset]

            amount_tokens = units_to_sell

        # action == "hold" -- no-op, amount_tokens stays 0.

        portfolio_value_after = self.get_total_value(agent_id, prices)

        return {
            "amount_tokens": round(amount_tokens, 8),
            "price": price,
            "portfolio_value_after": round(portfolio_value_after, 2),
            "realized_pnl": round(realized_pnl, 2),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def persist(self, agent_id: str, season_id: int) -> None:
        """Write the current in-memory state to the portfolios table (upsert)."""
        state = self._portfolios.get(agent_id)
        if state is None:
            return

        # Upsert ARENA (cash) row.
        await self.db.execute(
            """
            INSERT OR REPLACE INTO portfolios (agent_id, season_id, asset, units, avg_entry_price)
            VALUES (?, ?, 'ARENA', ?, 1.0)
            """,
            (agent_id, season_id, state["cash"]),
        )

        # Upsert each held asset.
        for asset, pos in state["positions"].items():
            await self.db.execute(
                """
                INSERT OR REPLACE INTO portfolios (agent_id, season_id, asset, units, avg_entry_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agent_id, season_id, asset, pos["units"], pos["avg_entry_price"]),
            )


# ---------------------------------------------------------------------------
# Self-test: create a PortfolioManager with a mock DB, init an agent,
# buy ETH, sell ETH, and print state at each step.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    class _MockDB:
        """Minimal stand-in so we can run the self-test without a real SQLite file."""

        async def execute(self, sql: str, params: tuple = ()) -> None:  # noqa: D102
            pass  # swallow writes

        async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:  # noqa: D102
            return None

        async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:  # noqa: D102
            return []

    async def _self_test() -> None:
        db = _MockDB()  # type: ignore[arg-type]
        pm = PortfolioManager(db)

        agent = "test-agent-001"
        season = 1

        # -- Init ----------------------------------------------------------
        await pm.init_agent(agent, season)
        prices = {
            "BTC": {"price_usd": 98500},
            "ETH": {"price_usd": 3800},
            "HBAR": {"price_usd": 0.28},
            "DOGE": {"price_usd": 0.18},
        }
        snap = pm.get_portfolio(agent, prices)
        print("=== After init ===")
        print(f"  Cash:  {snap['cash']}")
        print(f"  Value: {snap['total_value']}")
        print(f"  PnL%:  {snap['total_pnl_pct']}")
        print()

        # -- Buy 25% ETH ---------------------------------------------------
        assert pm.can_execute(agent, "buy", "ETH", 25, prices)
        result = pm.execute_trade(agent, "buy", "ETH", 25, prices)
        snap = pm.get_portfolio(agent, prices)
        print("=== After BUY 25% ETH @ $3800 ===")
        print(f"  Tokens bought: {result['amount_tokens']}")
        print(f"  Cash:  {snap['cash']}")
        print(f"  Positions: {snap['positions']}")
        print(f"  Value: {snap['total_value']}")
        print()

        # -- ETH price rises to $4000, then sell 100% ----------------------
        prices["ETH"]["price_usd"] = 4000
        snap_before_sell = pm.get_portfolio(agent, prices)
        print("=== ETH rises to $4000 (before sell) ===")
        print(f"  Value: {snap_before_sell['total_value']}")
        print(f"  Unrealized PnL on ETH: {snap_before_sell['positions'][0]['unrealized_pnl_pct']}%")
        print()

        assert pm.can_execute(agent, "sell", "ETH", 100, prices)
        result = pm.execute_trade(agent, "sell", "ETH", 100, prices)
        snap = pm.get_portfolio(agent, prices)
        print("=== After SELL 100% ETH @ $4000 ===")
        print(f"  Tokens sold: {result['amount_tokens']}")
        print(f"  Realized PnL: {result['realized_pnl']}")
        print(f"  Cash:  {snap['cash']}")
        print(f"  Positions: {snap['positions']}")
        print(f"  Value: {snap['total_value']}")
        print(f"  PnL%:  {snap['total_pnl_pct']}")
        print()

        # -- Edge cases -----------------------------------------------------
        assert not pm.can_execute(agent, "sell", "ETH", 50, prices), "Should not sell ETH (no longer held)"
        assert pm.can_execute(agent, "hold", "ETH", 0, prices), "HOLD should always be allowed"
        hold_result = pm.execute_trade(agent, "hold", "ETH", 0, prices)
        print("=== HOLD (no-op) ===")
        print(f"  Result: {hold_result}")
        print()

        print("All self-test checks passed.")

    asyncio.run(_self_test())
