"""FastAPI application for Agent League.

Wires together the database, Hedera client, market feed, portfolio manager,
orchestrator, and WebSocket manager into a single async application.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from engine.api.routes import router
from engine.api.websocket import WSManager
from engine.core.hedera_client import HederaClient
from engine.core.llm import warmup as llm_warmup
from engine.core.market import MarketFeed
from engine.core.orchestrator import Orchestrator
from engine.core.portfolio import PortfolioManager
from engine.db.database import Database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + WebSocket manager
# ---------------------------------------------------------------------------

app = FastAPI(title="Agent League", version="0.1.0")

ws_manager = WSManager()

# ---------------------------------------------------------------------------
# CORS — allow all origins (hackathon)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Root redirect → frontend dashboard
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return RedirectResponse(url="http://localhost:3001/dashboard")

# ---------------------------------------------------------------------------
# Include REST routes
# ---------------------------------------------------------------------------

app.include_router(router)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    """Initialize all subsystems and store them in app.state."""
    logger.info("Starting Agent League...")

    # 1. Database
    db = Database()
    await db.init()
    app.state.db = db
    logger.info("Database initialized")

    # 2. Hedera client
    hedera = HederaClient()
    app.state.hedera_client = hedera
    logger.info("Hedera client initialized (stub_mode=%s)", hedera.stub_mode)

    # 3. Market feed
    market = MarketFeed()
    app.state.market = market
    logger.info("Market feed initialized")

    # 4. Portfolio manager
    portfolio = PortfolioManager(db)
    app.state.portfolio = portfolio
    logger.info("Portfolio manager initialized")

    # 5. Orchestrator
    orchestrator = Orchestrator(
        db=db,
        hedera=hedera,
        market=market,
        portfolio=portfolio,
    )
    orchestrator.broadcast_callback = ws_manager.broadcast
    app.state.orchestrator = orchestrator
    logger.info("Orchestrator initialized")

    # 6. Warmup LLM connection
    await llm_warmup()
    logger.info("LLM connection warmed up")

    # 7. Auto-resume active season (if server restarted mid-season)
    active = await db.fetchone(
        "SELECT id FROM seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    )
    if active:
        # Mark old season as interrupted, start fresh
        await db.execute(
            "UPDATE seasons SET status = 'completed' WHERE id = ?",
            (active["id"],),
        )
        logger.info("Marked stale season %d as completed", active["id"])

    # 8. Auto-start a new season with any existing agents
    agent_count = await db.fetchone("SELECT COUNT(*) as c FROM agents WHERE status = 'active'")
    if agent_count and agent_count["c"] > 0:
        season_id = await orchestrator.start_season(total_rounds=0, interval_sec=30)
        logger.info("Auto-started season %d with %d agents", season_id, agent_count["c"])
    else:
        logger.info("No active agents — waiting for agents to be created")

    logger.info("Agent League ready!")


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


@app.on_event("shutdown")
async def shutdown():
    """Clean up resources."""
    db: Database | None = getattr(app.state, "db", None)
    if db is not None:
        await db.close()
    logger.info("Agent League shut down")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/live")
async def ws_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time trade/leaderboard broadcasts."""
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
