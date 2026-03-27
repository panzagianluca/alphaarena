"""Pydantic models for Agent League."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Action(str, Enum):
    buy = "buy"
    sell = "sell"
    hold = "hold"


class Asset(str, Enum):
    HBAR = "HBAR"
    BTC = "BTC"
    ETH = "ETH"
    DOGE = "DOGE"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Trade Decision (LLM output)
# ---------------------------------------------------------------------------

class TradeDecision(BaseModel):
    action: Action = Action.hold
    asset: Asset = Asset.NONE
    amount_pct: float = Field(default=0, ge=0, le=100)
    reasoning: str = ""
    confidence: float = Field(default=0, ge=0, le=1)
    mood: str = ""


# ---------------------------------------------------------------------------
# Agent Models
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    thesis: str
    creator_name: Optional[str] = None


class AgentProfile(BaseModel):
    id: str
    name: str
    thesis: str
    system_prompt: str
    hedera_account_id: str = ""
    creator_name: Optional[str] = None
    is_preset: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

class MarketTick(BaseModel):
    price_usd: float
    change_1h_pct: float = 0.0
    change_24h_pct: float = 0.0
    volume_trend: str = "stable"  # surging / stable / decreasing


# ---------------------------------------------------------------------------
# Round Context (input to LLM)
# ---------------------------------------------------------------------------

class RoundContext(BaseModel):
    round_number: int
    total_rounds: int
    market: dict[str, MarketTick]
    portfolio: dict  # flexible: cash, positions, total_value, etc.
    recent_trades: list[dict] = Field(default_factory=list)
    league_standings: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Thesis Generation (LLM output)
# ---------------------------------------------------------------------------

class ThesisGeneration(BaseModel):
    name: str
    system_prompt: str
