# Build Progress

## Method: RPIA per Phase
Each phase follows: **Research → Plan → Implement → Audit**
Multiple agents used per step to avoid bias/overfitting.

---

## Phase 0: Project Scaffolding + Dependencies
- **Status**: ✅ DONE
- **Started**: 2026-03-26
- **Note**: Python 3.14 incompatible with hedera-agent-kit (requires <3.14). Switched to Python 3.13.
- **Key finding**: `pip install git+...` fails — pyproject.toml is in `python/` subdir. Use `pip install hedera-agent-kit` from PyPI instead.
- **Files created**:
  - `engine/__init__.py` (and all subpackage inits)
  - `engine/requirements.txt`
  - `engine/.env.example`
  - `.gitignore`
  - `.venv/` (Python 3.13)
- **Verified imports**: openai, hedera-agent-kit, hiero-sdk-python, aiosqlite, fastapi

## Phase 1: Schemas + LLM Client
- **Status**: ✅ DONE
- **Files**: `engine/agents/schemas.py`, `engine/core/llm.py`
- **Models**: TradeDecision, AgentCreate, AgentProfile, MarketTick, RoundContext, ThesisGeneration
- **LLM functions**: get_trade_decision (Haiku 4.5, structured output), thesis_to_prompt, generate_commentary (Sonnet), warmup
- **Verified**: imports pass, retry logic + default hold fallback built-in

## Phase 2: Price Feed
- **Status**: ✅ DONE
- **Files**: `engine/core/market.py`
- **Class**: MarketFeed with fetch() (CoinGecko /coins/markets) + _mock_prices() fallback (random walk)
- **Features**: volume trend from cached readings, httpx async, timeout=5, auto-fallback on any error
- **Verified**: imports pass, self-test runs

## Phase 3: Database Layer
- **Status**: ✅ DONE
- **Files**: `engine/db/schema.sql`, `engine/db/database.py`
- **Tables**: agents, seasons, trades, portfolios, leaderboard, allocations, commentary
- **Features**: WAL mode, foreign keys, aiosqlite async, dict row factory
- **Verified**: self-test passes — creates tables, inserts, reads back, WAL confirmed

## Phase 4: Portfolio Tracker
- **Status**: ✅ DONE
- **Files**: `engine/core/portfolio.py`
- **Class**: PortfolioManager — in-memory state + DB persistence
- **Methods**: init_agent, get_portfolio, can_execute, execute_trade, persist, get_total_value
- **Verified**: self-test passes — buy 25% ETH → price rises → sell 100% → PnL correct ($131.58 profit)

## Phase 5: Scoring System
- **Status**: ✅ DONE
- **Files**: `engine/core/scoring.py`
- **Functions**: calculate_scores (PnL, Sharpe, win rate, max drawdown), rank_agents (normalize + composite)
- **Verified**: self-test passes — steady winner #1, volatile #2, loser #3. Edge cases handled (empty, single, ties)

## Phase 6: Hedera Client
- **Status**: ✅ DONE
- **Files**: `engine/core/hedera_client.py`, `engine/scripts/setup_hedera.py`, `engine/scripts/__init__.py`
- **Class**: HederaClient — dual-mode (LIVE SDK / STUB fallback)
- **Methods**: assign_wallet, fund_agent, execute_trade (bidirectional), publish_prices, publish_trade_reasoning, allocate_capital
- **Key design**: asyncio.Lock for treasury serialization, per-agent client caching for sells, stub mode logs operations without SDK
- **Note**: Real SDK calls stubbed with TODOs. Engine works end-to-end with tx_id=None. Wire up `hiero-sdk-python` calls when testnet account is available.

## Phase 7: Agent Base + Factory
- **Status**: ✅ DONE
- **Files**: `engine/agents/base.py`, `engine/agents/factory.py`, `engine/agents/templates.py`
- **TradingAgent**: dataclass with decide() → calls LLM with agent's system prompt
- **Factory**: create_agent (thesis→prompt→wallet→DB), load_agents, seed_presets (idempotent)
- **Verified**: all imports pass

## Phase 8: Orchestrator
- **Status**: ✅ DONE
- **Files**: `engine/core/orchestrator.py` (~390 lines)
- **Class**: Orchestrator — the brain that runs the game loop
- **Methods**: start_season, run_round (10-step core loop), tick (manual), run_loop (background), add_agent_mid_season
- **Key design**: parallel LLM calls, sequential Hedera, resilient error handling, broadcast callback for WebSocket
- **Verified**: imports pass

## Phase 9: FastAPI Backend
- **Status**: ✅ DONE
- **Files**: `engine/api/app.py`, `engine/api/routes.py`, `engine/api/websocket.py`, `engine/main.py`
- **Endpoints**: /api/agents/create, /api/agents/templates, /api/league, /api/agents, /api/agents/{id}, /api/season/start, /api/season/tick, /api/feed, /api/allocate
- **WebSocket**: /ws/live with dead-client cleanup
- **Startup**: init DB, Hedera, Market, Portfolio, Orchestrator, LLM warmup

## Phase 10: E2E Smoke Test
- **Status**: 🔄 READY TO RUN
- **Requires**: OpenRouter API key in engine/.env
