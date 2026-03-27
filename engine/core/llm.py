"""LLM integration via OpenRouter (OpenAI-compatible API)."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from engine.agents.schemas import ThesisGeneration, TradeDecision

load_dotenv()

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
    return _client


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

HAIKU = "anthropic/claude-haiku-4.5"
SONNET = "anthropic/claude-3.5-sonnet"

# ---------------------------------------------------------------------------
# JSON Schemas for structured output
# ---------------------------------------------------------------------------

TRADE_DECISION_SCHEMA = {
    "name": "trade_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
            "asset": {"type": "string", "enum": ["HBAR", "BTC", "ETH", "DOGE", "NONE"]},
            "amount_pct": {"type": "number"},
            "reasoning": {"type": "string"},
            "confidence": {"type": "number"},
            "mood": {"type": "string"},
        },
        "required": ["action", "asset", "amount_pct", "reasoning", "confidence", "mood"],
        "additionalProperties": False,
    },
}

THESIS_GENERATION_SCHEMA = {
    "name": "thesis_generation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "system_prompt": {"type": "string"},
        },
        "required": ["name", "system_prompt"],
        "additionalProperties": False,
    },
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

THESIS_SYSTEM_PROMPT = """\
You are an expert at turning trading theses into AI agent personalities.

Given a user's trading thesis, generate a JSON object with:
1. "name": A short memorable agent NAME (1 word, evocative)
2. "system_prompt": A complete system prompt that includes:
   - The agent's core trading PHILOSOPHY (2-3 sentences)
   - Specific numeric RULES (buy/sell triggers, position sizing %, cash reserve %)
   - The agent's VOICE (how it communicates its reasoning)

The system_prompt should start with "You are {name}, ..." and read as instructions to a trading AI.
"""

TRADE_SYSTEM_SUFFIX = """

You are in a COMPETITIVE trading arena. Other agents are actively trading to beat you. Passive agents finish last.

CRITICAL RULES:
- You MUST make a trade (buy or sell) at least every other round. Holding 2+ rounds in a row is a losing strategy.
- If you currently hold no positions, you MUST buy something. Cash sitting idle loses the competition.
- Be decisive. The market rewards conviction. Pick an asset and commit.
- Diversify OR concentrate — but DO something.

Analyze the market data and your portfolio, then decide your next move.

Respond with a JSON object:
- action: "buy", "sell", or "hold"
- asset: one of "HBAR", "BTC", "ETH", "DOGE", or "NONE" (use NONE for hold)
- amount_pct: percentage of available cash (for buy) or position (for sell), 0-100
- reasoning: 1-3 sentences explaining your decision
- confidence: 0.0 to 1.0
- mood: a short phrase describing your current sentiment
"""

# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------


async def get_trade_decision(
    system_prompt: str,
    context: dict,
    temperature: float = 0.7,
    model: str | None = None,
) -> TradeDecision:
    """Ask the LLM for a trade decision given the agent's prompt and market context."""
    client = _get_client()
    full_system = system_prompt + TRADE_SYSTEM_SUFFIX
    use_model = model or HAIKU

    for attempt in range(2):  # 1 retry on failure
        try:
            response = await client.chat.completions.create(
                model=use_model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": json.dumps(context)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": TRADE_DECISION_SCHEMA,
                },
            )

            raw = json.loads(response.choices[0].message.content)
            decision = TradeDecision(**raw)

            # Post-validate: if hold, zero out amount and set asset to NONE
            if decision.action == "hold":
                decision.amount_pct = 0
                decision.asset = "NONE"

            return decision

        except Exception:
            if attempt == 0:
                continue  # retry once
            # Final failure -> safe default
            return TradeDecision(
                action="hold",
                asset="NONE",
                amount_pct=0,
                reasoning="Failed to decide",
                confidence=0,
                mood="error",
            )

    # Unreachable, but satisfies type checker
    return TradeDecision(
        action="hold",
        asset="NONE",
        amount_pct=0,
        reasoning="Failed to decide",
        confidence=0,
        mood="error",
    )


async def thesis_to_prompt(thesis: str) -> ThesisGeneration:
    """Convert a plain-text trading thesis into an agent name + system prompt."""
    client = _get_client()

    response = await client.chat.completions.create(
        model=HAIKU,
        temperature=0.7,
        messages=[
            {"role": "system", "content": THESIS_SYSTEM_PROMPT},
            {"role": "user", "content": thesis},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": THESIS_GENERATION_SCHEMA,
        },
    )

    raw = json.loads(response.choices[0].message.content)
    return ThesisGeneration(**raw)


async def generate_commentary(round_data: dict) -> str:
    """Generate dramatic commentary for a trading round."""
    client = _get_client()

    try:
        response = await client.chat.completions.create(
            model=SONNET,
            temperature=0.9,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a dramatic sports-style commentator for an AI trading competition. "
                        "Given the round data, write 2-3 sentences of exciting commentary about "
                        "what just happened. Be colorful, use trading and sports metaphors. Keep it short."
                    ),
                },
                {"role": "user", "content": json.dumps(round_data)},
            ],
        )
        return response.choices[0].message.content or ""
    except Exception:
        return ""


async def warmup() -> None:
    """Make a throwaway call to pre-warm the OpenRouter connection."""
    client = _get_client()
    try:
        await client.chat.completions.create(
            model=HAIKU,
            messages=[{"role": "user", "content": "Say 'ready' in one word."}],
            max_tokens=5,
        )
    except Exception:
        pass  # warmup failure is not critical


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _test():
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("OPENROUTER_API_KEY not set -- skipping live test")
            return

        print("Testing thesis_to_prompt...")
        result = await thesis_to_prompt(
            "I'm bullish on ETH. Buy every dip >3%. Never hold memecoins. Keep 20% cash."
        )
        print(f"  Name: {result.name}")
        print(f"  System prompt: {result.system_prompt[:200]}...")
        print("Done.")

    asyncio.run(_test())
