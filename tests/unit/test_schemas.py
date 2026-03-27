"""Tests for engine.agents.schemas Pydantic models."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from engine.agents.schemas import (
    Action,
    AgentCreate,
    AgentProfile,
    Asset,
    MarketTick,
    RoundContext,
    ThesisGeneration,
    TradeDecision,
)


# ---------------------------------------------------------------------------
# TradeDecision
# ---------------------------------------------------------------------------

class TestTradeDecision:
    def test_valid_buy(self):
        td = TradeDecision(
            action="buy", asset="ETH", amount_pct=25,
            reasoning="ETH dip", confidence=0.8, mood="bullish",
        )
        assert td.action == Action.buy
        assert td.asset == Asset.ETH
        assert td.amount_pct == 25

    def test_valid_hold(self):
        td = TradeDecision(
            action="hold", asset="NONE", amount_pct=0,
            reasoning="waiting", confidence=0.5, mood="neutral",
        )
        assert td.action == Action.hold
        assert td.asset == Asset.NONE

    def test_defaults(self):
        td = TradeDecision()
        assert td.action == Action.hold
        assert td.asset == Asset.NONE
        assert td.amount_pct == 0
        assert td.reasoning == ""
        assert td.confidence == 0
        assert td.mood == ""

    def test_amount_pct_min_boundary(self):
        td = TradeDecision(action="buy", asset="BTC", amount_pct=0,
                           reasoning="x", confidence=0.5, mood="x")
        assert td.amount_pct == 0

    def test_amount_pct_max_boundary(self):
        td = TradeDecision(action="buy", asset="BTC", amount_pct=100,
                           reasoning="x", confidence=0.5, mood="x")
        assert td.amount_pct == 100

    def test_amount_pct_over_100_rejected(self):
        with pytest.raises(ValidationError):
            TradeDecision(action="buy", asset="BTC", amount_pct=101,
                          reasoning="x", confidence=0.5, mood="x")

    def test_amount_pct_negative_rejected(self):
        with pytest.raises(ValidationError):
            TradeDecision(action="buy", asset="BTC", amount_pct=-1,
                          reasoning="x", confidence=0.5, mood="x")

    def test_confidence_range(self):
        TradeDecision(action="hold", asset="NONE", amount_pct=0,
                      reasoning="x", confidence=0.0, mood="x")
        TradeDecision(action="hold", asset="NONE", amount_pct=0,
                      reasoning="x", confidence=1.0, mood="x")

    def test_confidence_over_1_rejected(self):
        with pytest.raises(ValidationError):
            TradeDecision(action="hold", asset="NONE", amount_pct=0,
                          reasoning="x", confidence=1.1, mood="x")

    def test_confidence_negative_rejected(self):
        with pytest.raises(ValidationError):
            TradeDecision(action="hold", asset="NONE", amount_pct=0,
                          reasoning="x", confidence=-0.1, mood="x")

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            TradeDecision(action="yolo", asset="BTC", amount_pct=50,
                          reasoning="x", confidence=0.5, mood="x")

    def test_invalid_asset_rejected(self):
        with pytest.raises(ValidationError):
            TradeDecision(action="buy", asset="SOL", amount_pct=50,
                          reasoning="x", confidence=0.5, mood="x")

    def test_enum_values(self):
        assert set(Action) == {Action.buy, Action.sell, Action.hold}
        assert set(Asset) == {Asset.HBAR, Asset.BTC, Asset.ETH, Asset.DOGE, Asset.NONE}


# ---------------------------------------------------------------------------
# AgentCreate
# ---------------------------------------------------------------------------

class TestAgentCreate:
    def test_with_creator(self):
        ac = AgentCreate(thesis="Buy ETH dips", creator_name="Alice")
        assert ac.thesis == "Buy ETH dips"
        assert ac.creator_name == "Alice"

    def test_without_creator(self):
        ac = AgentCreate(thesis="YOLO everything")
        assert ac.creator_name is None

    def test_thesis_required(self):
        with pytest.raises(ValidationError):
            AgentCreate()


# ---------------------------------------------------------------------------
# AgentProfile
# ---------------------------------------------------------------------------

class TestAgentProfile:
    def test_full_profile(self):
        ap = AgentProfile(
            id="eth-maxi-abc",
            name="EthMaxi",
            thesis="Buy ETH",
            system_prompt="You are EthMaxi...",
            hedera_account_id="0.0.12345",
            creator_name="Bob",
            is_preset=True,
            status="active",
        )
        assert ap.id == "eth-maxi-abc"
        assert ap.is_preset is True
        assert isinstance(ap.created_at, datetime)

    def test_defaults(self):
        ap = AgentProfile(
            id="a", name="A", thesis="t", system_prompt="sp",
        )
        assert ap.hedera_account_id == ""
        assert ap.creator_name is None
        assert ap.is_preset is False
        assert ap.status == "active"


# ---------------------------------------------------------------------------
# MarketTick
# ---------------------------------------------------------------------------

class TestMarketTick:
    def test_full(self):
        mt = MarketTick(
            price_usd=3800.0, change_1h_pct=-2.3,
            change_24h_pct=5.1, volume_trend="surging",
        )
        assert mt.price_usd == 3800.0
        assert mt.volume_trend == "surging"

    def test_defaults(self):
        mt = MarketTick(price_usd=100.0)
        assert mt.change_1h_pct == 0.0
        assert mt.change_24h_pct == 0.0
        assert mt.volume_trend == "stable"


# ---------------------------------------------------------------------------
# RoundContext
# ---------------------------------------------------------------------------

class TestRoundContext:
    def test_full(self):
        ctx = RoundContext(
            round_number=5,
            total_rounds=30,
            market={
                "ETH": MarketTick(price_usd=3800),
                "BTC": MarketTick(price_usd=98000),
            },
            portfolio={"cash_ARENA": 10000, "positions": []},
            recent_trades=[{"round": 4, "action": "buy"}],
            league_standings=[{"rank": 1, "agent": "Viper", "pnl_pct": 5.0}],
        )
        assert ctx.round_number == 5
        assert len(ctx.market) == 2
        assert ctx.market["ETH"].price_usd == 3800

    def test_defaults(self):
        ctx = RoundContext(
            round_number=1, total_rounds=10,
            market={}, portfolio={},
        )
        assert ctx.recent_trades == []
        assert ctx.league_standings == []


# ---------------------------------------------------------------------------
# ThesisGeneration
# ---------------------------------------------------------------------------

class TestThesisGeneration:
    def test_valid(self):
        tg = ThesisGeneration(name="Viper", system_prompt="You are Viper...")
        assert tg.name == "Viper"

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ThesisGeneration(name="X")
        with pytest.raises(ValidationError):
            ThesisGeneration(system_prompt="Y")
