"""
TradingAgent — the core agent abstraction for Agent League.

An agent is just a system prompt + a wallet.  All intelligence comes from the
LLM call.  The class is intentionally minimal: a dataclass with a single
``decide`` method that calls the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.agents.schemas import RoundContext, TradeDecision
from engine.core.llm import get_trade_decision


@dataclass
class TradingAgent:
    """One autonomous trading agent in the league."""

    id: str
    name: str
    thesis: str
    system_prompt: str
    hedera_account_id: str
    hedera_private_key: str  # needed for agent-signed sell transactions
    creator_name: str = ""
    is_preset: bool = False
    temperature: float = 0.7
    wallet_index: int = -1  # index in wallets.json pool
    model: str = ""  # OpenRouter model ID (empty = use default)

    async def decide(self, context: RoundContext) -> TradeDecision:
        """Call the LLM with this agent's personality and the current market context.

        Returns a :class:`TradeDecision` — buy / sell / hold with reasoning.
        On LLM failure the underlying ``get_trade_decision`` returns a safe
        "hold" default, so this method never raises.
        """
        return await get_trade_decision(
            system_prompt=self.system_prompt,
            context=context.model_dump(),
            temperature=self.temperature,
            model=self.model if self.model else None,
        )


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Demonstrate creating a TradingAgent without real Hedera / LLM calls.
    agent = TradingAgent(
        id="demo-abc1",
        name="DemoBot",
        thesis="Buy ETH dips, hold BTC long term.",
        system_prompt="You are DemoBot, a cautious ETH-focused trader...",
        hedera_account_id="0.0.12345",
        hedera_private_key="302e..fake",
        creator_name="demo_user",
        is_preset=False,
        temperature=0.7,
        wallet_index=0,
    )
    print(f"Agent created: {agent.id} ({agent.name})")
    print(f"  thesis:     {agent.thesis[:60]}...")
    print(f"  account:    {agent.hedera_account_id}")
    print(f"  preset:     {agent.is_preset}")
    print(f"  temperature:{agent.temperature}")
