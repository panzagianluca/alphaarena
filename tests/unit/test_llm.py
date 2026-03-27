"""Tests for engine.core.llm -- uses mocked OpenAI client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.agents.schemas import TradeDecision, ThesisGeneration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(content: str):
    """Build a fake OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_mock_client(response_content: str):
    """Return an AsyncMock client whose .chat.completions.create returns a canned response."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_response(response_content),
    )
    return client


# ---------------------------------------------------------------------------
# get_trade_decision
# ---------------------------------------------------------------------------

class TestGetTradeDecision:
    @pytest.mark.asyncio
    async def test_returns_valid_buy(self):
        payload = json.dumps({
            "action": "buy", "asset": "ETH", "amount_pct": 25,
            "reasoning": "dip buying", "confidence": 0.8, "mood": "bullish",
        })
        mock_client = _make_mock_client(payload)

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import get_trade_decision
            td = await get_trade_decision("You are EthMaxi", {"round": 1})

        assert td.action == "buy"
        assert td.asset == "ETH"
        assert td.amount_pct == 25
        assert td.confidence == 0.8

    @pytest.mark.asyncio
    async def test_hold_clamps_amount_and_asset(self):
        """When action is hold, amount_pct must be 0 and asset NONE."""
        payload = json.dumps({
            "action": "hold", "asset": "BTC", "amount_pct": 50,
            "reasoning": "waiting", "confidence": 0.5, "mood": "neutral",
        })
        mock_client = _make_mock_client(payload)

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import get_trade_decision
            td = await get_trade_decision("prompt", {})

        assert td.action == "hold"
        assert td.amount_pct == 0
        assert td.asset == "NONE"

    @pytest.mark.asyncio
    async def test_failure_returns_default_hold(self):
        """On LLM failure (after retry), return a safe default hold."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API down"),
        )

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import get_trade_decision
            td = await get_trade_decision("prompt", {})

        assert td.action == "hold"
        assert td.asset == "NONE"
        assert td.amount_pct == 0
        assert td.reasoning == "Failed to decide"
        assert td.confidence == 0
        assert td.mood == "error"

    @pytest.mark.asyncio
    async def test_retries_once_then_succeeds(self):
        """First call fails, second succeeds."""
        good_payload = json.dumps({
            "action": "sell", "asset": "DOGE", "amount_pct": 100,
            "reasoning": "dump it", "confidence": 0.9, "mood": "bearish",
        })
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[Exception("transient"), _mock_response(good_payload)],
        )

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import get_trade_decision
            td = await get_trade_decision("prompt", {})

        assert td.action == "sell"
        assert td.asset == "DOGE"

    @pytest.mark.asyncio
    async def test_custom_temperature_passed(self):
        payload = json.dumps({
            "action": "hold", "asset": "NONE", "amount_pct": 0,
            "reasoning": "pass", "confidence": 0.1, "mood": "calm",
        })
        mock_client = _make_mock_client(payload)

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import get_trade_decision
            await get_trade_decision("prompt", {}, temperature=0.3)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.3


# ---------------------------------------------------------------------------
# thesis_to_prompt
# ---------------------------------------------------------------------------

class TestThesisToPrompt:
    @pytest.mark.asyncio
    async def test_returns_thesis_generation(self):
        payload = json.dumps({
            "name": "EthMaxi",
            "system_prompt": "You are EthMaxi, a disciplined ETH trader...",
        })
        mock_client = _make_mock_client(payload)

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import thesis_to_prompt
            result = await thesis_to_prompt("Buy ETH dips")

        assert isinstance(result, ThesisGeneration)
        assert result.name == "EthMaxi"
        assert "EthMaxi" in result.system_prompt

    @pytest.mark.asyncio
    async def test_uses_haiku_model(self):
        payload = json.dumps({"name": "X", "system_prompt": "Y"})
        mock_client = _make_mock_client(payload)

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import thesis_to_prompt
            await thesis_to_prompt("anything")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-haiku-4.5"

    @pytest.mark.asyncio
    async def test_uses_json_schema_format(self):
        payload = json.dumps({"name": "X", "system_prompt": "Y"})
        mock_client = _make_mock_client(payload)

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import thesis_to_prompt
            await thesis_to_prompt("anything")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        rf = call_kwargs["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["strict"] is True


# ---------------------------------------------------------------------------
# generate_commentary
# ---------------------------------------------------------------------------

class TestGenerateCommentary:
    @pytest.mark.asyncio
    async def test_returns_string(self):
        mock_client = _make_mock_client("What a round! EthMaxi goes all in!")

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import generate_commentary
            result = await generate_commentary({"round": 5, "trades": []})

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_uses_sonnet_model(self):
        mock_client = _make_mock_client("commentary")

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import generate_commentary
            await generate_commentary({})

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-3.5-sonnet"

    @pytest.mark.asyncio
    async def test_failure_returns_empty_string(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error"),
        )

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import generate_commentary
            result = await generate_commentary({})

        assert result == ""


# ---------------------------------------------------------------------------
# warmup
# ---------------------------------------------------------------------------

class TestWarmup:
    @pytest.mark.asyncio
    async def test_warmup_calls_haiku(self):
        mock_client = _make_mock_client("ready")

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import warmup
            await warmup()

        mock_client.chat.completions.create.assert_awaited_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-haiku-4.5"

    @pytest.mark.asyncio
    async def test_warmup_failure_does_not_raise(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("connection refused"),
        )

        with patch("engine.core.llm._get_client", return_value=mock_client):
            from engine.core.llm import warmup
            await warmup()  # should not raise
