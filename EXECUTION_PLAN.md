# Execution Plan — Engine Only (No UI)

Everything here is Python. The frontend is a separate step after this works end-to-end.

**Goal**: Run a full season from the command line — 4+ agents trading, real HTS transfers on Hedera testnet, prices + reasoning published to HCS topics, real capital allocation, leaderboard updating — with a FastAPI backend serving the data over REST + WebSocket.

**Everything on-chain**: HTS for token transfers, HCS for price logs + trade reasoning. Not simulated.

---

## Phase 0: Project Scaffolding + Dependencies (30 min)

### 0.1 Create directory structure
```
engine/
├── agents/
│   ├── __init__.py
│   ├── base.py
│   ├── factory.py
│   ├── templates.py
│   └── schemas.py
├── core/
│   ├── __init__.py
│   ├── llm.py
│   ├── hedera_client.py
│   ├── market.py
│   ├── portfolio.py
│   ├── scoring.py
│   └── orchestrator.py
├── api/
│   ├── __init__.py
│   ├── app.py
│   ├── routes.py
│   └── websocket.py
├── db/
│   ├── __init__.py
│   ├── database.py
│   └── schema.sql
├── scripts/
│   ├── setup_hedera.py
│   └── seed_presets.py
├── requirements.txt
├── .env.example
└── main.py
```

### 0.2 requirements.txt
```
# LLM
openai>=1.0

# Hedera
# Install separately: pip install git+https://github.com/hashgraph/hedera-agent-kit-py.git

# Backend
fastapi>=0.104
uvicorn[standard]>=0.24
websockets>=12.0
aiosqlite>=0.19

# Utils
python-dotenv>=1.0
httpx>=0.25
pydantic>=2.0
```

### 0.3 .env.example
```
OPENROUTER_API_KEY=sk-or-v1-xxxx
HEDERA_ACCOUNT_ID=0.0.xxxxx
HEDERA_PRIVATE_KEY=302...
WALLET_POOL_PATH=./wallets.json
TOKEN_ARENA_ID=
TOKEN_WHBAR_ID=
TOKEN_WBTC_ID=
TOKEN_WETH_ID=
TOKEN_WDOGE_ID=
```

### 0.3 Verify
- [ ] `pip install -r requirements.txt` succeeds
- [ ] `pip install git+https://github.com/hashgraph/hedera-agent-kit-py.git` succeeds
- [ ] `python -c "from openai import OpenAI; print('ok')"` works
- [ ] `python -c "from hedera_agent_kit.shared.api import HederaAgentAPI; print('ok')"` works

---

## Phase 1: Schemas + LLM Client (45 min)

Build the data models and LLM integration first. These have zero external dependencies (just OpenRouter) and can be tested immediately.

### 1.1 `engine/agents/schemas.py`
Pydantic models:
- `TradeDecision`: action (buy/sell/hold), asset, amount_pct, reasoning, confidence, mood
- `AgentCreate`: thesis (str), creator_name (optional str)
- `AgentProfile`: id, name, thesis, system_prompt, hedera_account_id, creator_name, is_preset
- `MarketData`: dict of asset → { price_usd, change_1h_pct, change_24h_pct, volume_trend }
- `RoundContext`: round number, total rounds, market data, portfolio, recent trades, standings
- `ThesisGeneration`: name (str), system_prompt (str)

### 1.2 `engine/core/llm.py`
Three functions, all using OpenRouter via the `openai` package:

**`get_trade_decision(system_prompt: str, context: RoundContext) → TradeDecision`**
- Calls `anthropic/claude-haiku-4.5` with `response_format.json_schema` (strict)
- Schema enforces: action enum, asset enum, amount_pct 0-100, confidence 0-1
- Post-validate: if action=="hold", clamp amount_pct=0
- On failure: 1 retry, then return TradeDecision(action="hold", ...)
- Temperature: 0.7 (configurable per agent)

**`thesis_to_prompt(thesis: str) → ThesisGeneration`**
- Calls `anthropic/claude-haiku-4.5` with json_schema
- Prompt forces: agent name, philosophy, numeric buy/sell triggers, position sizing rules, cash reserve %, voice
- Returns: { name: "EthMaxi", system_prompt: "You are EthMaxi..." }

**`generate_commentary(round_data: dict) → str`**
- Calls `anthropic/claude-3.5-sonnet` (richer narration)
- Returns dramatic commentary string
- On failure: return empty string (non-critical)

**`_warmup()`**
- Called at app startup
- Makes one throwaway Haiku call to warm the OpenRouter connection
- Prevents cold-start latency during live demo

### 1.3 Verify
- [ ] `thesis_to_prompt("I like ETH, buy dips")` returns valid name + system_prompt
- [ ] `get_trade_decision(prompt, fake_context)` returns valid TradeDecision
- [ ] `generate_commentary(fake_round)` returns a string
- [ ] Failed LLM call returns default "hold" decision

---

## Phase 2: Price Feed (30 min)

### 2.1 `engine/core/market.py`

**`MarketFeed` class:**
- `async fetch() → dict[str, MarketData]` — returns prices for HBAR, BTC, ETH, DOGE
- Uses CoinGecko `/coins/markets` endpoint with `price_change_percentage=1h,24h`
- `timeout=5` on every request
- On ANY exception → falls back to `_mock_prices()`
- Caches last 2 volume readings to compute `volume_trend` (surging/stable/decreasing)
- Maps CoinGecko IDs to our symbols: `hedera-hashgraph→HBAR`, `bitcoin→BTC`, etc.

**`_mock_prices()` fallback:**
- Maintains internal state: last price per asset
- Each call: `price *= random.uniform(0.97, 1.03)` per asset
- Volume: `random.uniform(0.8, 1.5) * base_volume`
- Starting prices: BTC=98000, ETH=3800, HBAR=0.28, DOGE=0.18

### 2.2 Verify
- [ ] `await feed.fetch()` returns 4 assets with prices
- [ ] Disconnect WiFi → mock prices returned (no crash)
- [ ] Volume trend computed from 2+ readings

---

## Phase 3: Database Layer (30 min)

### 3.1 `engine/db/schema.sql`
All CREATE TABLE statements from PRD (agents, seasons, trades, portfolios, leaderboard, allocations, commentary).

### 3.2 `engine/db/database.py`

**`Database` class:**
- Uses `aiosqlite` for async access
- On init: `PRAGMA journal_mode=WAL`
- `async init()` — creates tables from schema.sql if not exists
- `async execute(sql, params)` — write
- `async fetchone(sql, params)` — single row
- `async fetchall(sql, params)` — multiple rows
- Connection created once, reused (with `check_same_thread=False` equivalent in aiosqlite)

### 3.3 Verify
- [ ] `db.init()` creates `league.db` with all tables
- [ ] Can insert and read back an agent row
- [ ] WAL mode confirmed: `PRAGMA journal_mode` returns `wal`

---

## Phase 4: Portfolio Tracker (45 min)

### 4.1 `engine/core/portfolio.py`

**`PortfolioManager` class:**
- Tracks each agent's holdings in memory (dict) + persists to DB
- `init_agent(agent_id, season_id)` — sets starting cash (10,000 ARENA), zero positions
- `get_portfolio(agent_id) → dict` — current holdings, cash, total value at current prices
- `can_execute(agent_id, decision, prices) → bool` — validates: enough cash for buy, enough units for sell
- `execute_trade(agent_id, decision, prices) → TradeRecord` — updates holdings, computes PnL
  - BUY: deduct cash, add units at current price, update avg_entry_price
  - SELL: remove units, add cash, compute realized PnL
  - HOLD: no-op, return trade record with reasoning
- `get_total_value(agent_id, prices) → float` — sum of (units * price) + cash
- `persist(agent_id, season_id)` — write current state to portfolios table

Key: portfolio operates in "ARENA units" mapped to USD via prices. 10,000 ARENA ≈ $10,000 starting capital.

### 4.2 Verify
- [ ] Init agent with 10,000 → buy 25% ETH at $3800 → portfolio shows ~2500 in ETH, ~7500 cash
- [ ] Sell ETH at $4000 → cash increases, PnL positive
- [ ] Can't buy more than cash balance
- [ ] Can't sell more than held units

---

## Phase 5: Scoring System (30 min)

### 5.1 `engine/core/scoring.py`

**`calculate_scores(agent_id, season_id, trades, current_value, starting_value) → dict`**

Returns:
- `pnl_pct`: (current - starting) / starting * 100
- `sharpe_ratio`: mean(round_returns) / std(round_returns) * sqrt(n_rounds). Returns 0 if < 3 trades.
- `win_rate`: profitable_trades / total_non_hold_trades * 100. Returns 0 if no trades.
- `max_drawdown_pct`: max peak-to-trough decline across portfolio_value_after sequence
- `total_trades`: count of non-hold trades
- `composite_score`: 0.4*norm(pnl) + 0.25*norm(sharpe) + 0.15*norm(win_rate) - 0.2*norm(drawdown)

**`rank_agents(all_agent_scores) → list`**
- Sort by composite_score descending
- Assign rank 1, 2, 3...
- Persist to leaderboard table

### 5.2 Verify
- [ ] Agent with +10% PnL, 60% win rate, low drawdown scores higher than -5% PnL agent
- [ ] Sharpe returns 0 with < 3 data points (not NaN/crash)
- [ ] Rankings are deterministic and correct

---

## Phase 6: Hedera Client (2h — the hardest part)

### 6.1 `engine/core/hedera_client.py`

**`HederaClient` class:**

**Init:**
- Create `Client` with testnet network
- Set operator to treasury account (from env vars)
- Load wallet pool from `wallets.json`
- Load HCS topic IDs from env vars
- Create an `asyncio.Queue` for sequential transaction submission
- Start `_tx_worker()` background task

**`assign_wallet() → WalletInfo`**
- Finds next unassigned wallet from pool
- Marks it as assigned in wallets.json
- Returns { index, account_id, private_key }
- Raises if pool exhausted

**`fund_agent(agent_account_id: str, amount: int) → str`**
- Airdrops ARENA tokens from treasury to agent
- Uses `AIRDROP_FUNGIBLE_TOKEN_TOOL` via `HederaAgentAPI.run()`
- Returns transaction ID
- Submitted through the sequential queue

**`execute_trade(trade: TradeRecord, agent_wallet: WalletInfo) → str | None`**
- BUY: treasury signs → airdrop wrapped asset token (wBTC/wETH/wHBAR/wDOGE) to agent. One tx.
- SELL: two txns:
  1. Agent signs → sends wrapped token back to treasury (using per-agent client)
  2. Treasury signs → airdrops ARENA back to agent
- HOLD: no transaction, returns None
- Treasury operations go through `asyncio.Queue`. Agent sends use per-agent clients (own nonce space).
- Returns hedera_tx_id (or tuple of tx_ids for sells) or None
- On failure: log error, return None (trade still recorded in DB, just without on-chain proof)

**`_get_agent_client(wallet: WalletInfo) → Client`**
- Lazily creates and caches a Hedera `Client` instance per agent wallet
- Used for agent-signed transactions (sells)
- Different account = different nonce = no conflict with treasury

**`publish_prices(prices: dict) → str | None`**
- Publishes current round's price data to the HCS Price Oracle topic
- Uses `SUBMIT_TOPIC_MESSAGE_TOOL` via `HederaAgentAPI.run()`
- Message: JSON with round, timestamp, all asset prices
- Returns topic sequence number / tx_id
- Submitted through the sequential queue (before trade executions)

**`publish_trade_reasoning(agent_name: str, decision: TradeDecision, hedera_tx_id: str) → str | None`**
- Publishes trade decision + reasoning to the HCS Trade Reasoning topic
- Uses `SUBMIT_TOPIC_MESSAGE_TOOL`
- Message: JSON with agent name, round, action, asset, amount, reasoning, confidence, linked tx_id
- Returns topic sequence number / tx_id
- Submitted through the queue (after trade execution, so we have the tx_id to reference)

**`allocate_capital(agent_account_id: str, amount: int) → str`**
- Real ARENA transfer from treasury to agent wallet
- The agent now has more capital for trading
- Returns hedera_tx_id
- Submitted through the sequential queue

**`_tx_worker()` (background task)**
- Runs forever, pulls from the asyncio.Queue
- Executes one Hedera transaction at a time (HTS transfers + HCS messages)
- Prevents treasury nonce conflicts
- Returns result via asyncio.Future attached to each queue item

### 6.2 `engine/scripts/setup_hedera.py`
One-time setup script (run manually before first use):
1. Connect to testnet with treasury account
2. Create 15 accounts via `CREATE_ACCOUNT_TOOL` with `max_automatic_token_associations=-1`
3. Create 5 HTS tokens with `decimals=6`, `initial_supply=1000000`, `is_supply_key=True`
4. Create 2 HCS topics via `CREATE_TOPIC_TOOL`:
   - Price Oracle Log topic (memo: "Agent League - Price Oracle")
   - Trade Reasoning Log topic (memo: "Agent League - Trade Decisions")
5. Write everything to `wallets.json` (wallets + token IDs + topic IDs)
6. Print env vars for `.env`

### 6.3 Verify
- [ ] `setup_hedera.py` creates 15 accounts + 5 tokens + 2 HCS topics on testnet
- [ ] `assign_wallet()` returns a valid wallet, second call returns a different one
- [ ] `fund_agent(account, 10000)` sends ARENA, visible on HashScan
- [ ] `execute_trade(buy_ETH)` sends wETH to agent, returns tx_id
- [ ] `publish_prices({...})` publishes to HCS topic, visible on HashScan under the topic
- [ ] `publish_trade_reasoning(...)` publishes reasoning to HCS topic
- [ ] `allocate_capital(agent, 1000)` sends ARENA to agent, returns tx_id
- [ ] Two concurrent transactions don't cause nonce errors (queue serializes them)
- [ ] Failed transaction returns None, doesn't crash

---

## Phase 7: Agent Base Class + Factory (45 min)

### 7.1 `engine/agents/base.py`

**`TradingAgent` class:**
```python
class TradingAgent:
    id: str
    name: str
    thesis: str
    system_prompt: str
    hedera_account_id: str
    temperature: float = 0.7

    async def decide(self, context: RoundContext) -> TradeDecision:
        """Call LLM with this agent's personality + current market context"""
        return await get_trade_decision(
            system_prompt=self.system_prompt,
            context=context,
            temperature=self.temperature,
        )
```

That's it. The agent is just a system prompt + a wallet. All the intelligence is in the LLM call.

### 7.2 `engine/agents/factory.py`

**`create_agent(thesis: str, creator_name: str | None, db, hedera) → TradingAgent`**
1. Call `thesis_to_prompt(thesis)` → get name + system_prompt
2. Call `hedera.assign_wallet()` → get wallet
3. Call `hedera.fund_agent(wallet.account_id, 10000)` → fund with ARENA
4. Generate agent ID (slugified name + short uuid)
5. Insert into DB: agents table + initial portfolio
6. Return TradingAgent instance

**`load_agents(db) → list[TradingAgent]`**
- Load all active agents from DB
- Return as TradingAgent instances

### 7.3 `engine/agents/templates.py`

4 preset thesis strings:
- `CONSERVATIVE_THESIS`: capital preservation, 10% max risk, 30% cash, cut at -5%
- `CONTRARIAN_THESIS`: buy fear, sell euphoria, 15-30% positions
- `MOMENTUM_THESIS`: ride breakouts, size up winners, 60% single asset ok
- `DEGEN_THESIS`: YOLO, 80% single position, vibes-based, full send

### 7.4 `engine/scripts/seed_presets.py`
- For each template thesis: call `create_agent(thesis, creator_name="System", ...)`
- Creates 4 preset agents in DB with wallets and ARENA funding
- Idempotent: skips if agents already exist

### 7.5 Verify
- [ ] `create_agent("I like ETH")` → generates name, assigns wallet, funds ARENA, returns agent
- [ ] `seed_presets.py` creates 4 agents
- [ ] `load_agents()` returns all 4
- [ ] Each agent has a different system_prompt
- [ ] Each agent has a valid Hedera account_id

---

## Phase 8: Orchestrator (1h — ties everything together)

### 8.1 `engine/core/orchestrator.py`

**`Orchestrator` class:**

**State:**
- `db: Database`
- `hedera: HederaClient`
- `market: MarketFeed`
- `portfolio: PortfolioManager`
- `agents: list[TradingAgent]`
- `season_id: int | None`
- `round_number: int`
- `broadcast_callback: Callable` — sends data to WebSocket manager

**`async start_season(total_rounds=30, interval_sec=30)`**
1. Load all active agents from DB
2. **Sweep all wallets clean** (AUDIT FIX #4):
   - For each agent: send all wrapped tokens (wBTC/wETH/wHBAR/wDOGE) back to treasury (agent-signed)
   - For each agent: send all ARENA back to treasury (agent-signed)
   - This reconciles on-chain state to zero
3. Re-fund each agent with 10,000 ARENA from treasury
4. Init portfolios in DB for each agent (10,000 ARENA cash, zero positions)
5. Create season row in DB
6. Start the round loop

**`async run_round()`**
The core loop — one iteration:
```
1. Fetch prices (market.fetch())
2. Publish prices to HCS (hedera.publish_prices())            ← ON-CHAIN PRICE LOG
3. Build RoundContext for each agent (market + portfolio + standings)
4. All agents decide in PARALLEL:
   decisions = await asyncio.gather(*[agent.decide(ctx) for agent, ctx in agent_contexts])
5. For each decision SEQUENTIALLY:
   a. portfolio.can_execute() → validate
   b. portfolio.execute_trade() → update holdings in memory
   c. hedera.execute_trade(decision, agent_wallet) → on-chain:
      - BUY: treasury airdrops wrapped token to agent          (treasury signs)
      - SELL: agent sends wrapped token to treasury             (agent signs)
           + treasury airdrops ARENA to agent                   (treasury signs)
      - HOLD: no tx
   d. hedera.publish_trade_reasoning() → HCS log              ← ON-CHAIN REASONING
   e. db.execute() → INSERT trade row (with all tx_ids)
6. scoring.rank_agents() → recalculate leaderboard
7. db.execute() → UPDATE leaderboard table
8. broadcast_callback({ trades, leaderboard, round_number })
9. Every 3rd round: generate_commentary() → broadcast
```

**`async tick()`**
- Manually trigger one round (for demo control via API)
- Same as run_round() but doesn't wait for interval

**`async run_loop()`**
- Background task: `while season active: await run_round(); await asyncio.sleep(interval)`

**`async add_agent_mid_season(agent: TradingAgent)`**
- Adds a newly created agent to the running season
- Inits portfolio, appends to agents list
- Agent participates starting next round

### 8.2 Verify (THE BIG TEST)
- [ ] `start_season()` with 4 preset agents → round loop runs
- [ ] Each round: prices published to HCS topic (verify on HashScan → topic messages)
- [ ] Each round: 4 LLM calls happen in parallel (~2s)
- [ ] Each round: 4 HTS transfers happen sequentially (verify on HashScan)
- [ ] Each round: 4 trade reasonings published to HCS topic (verify on HashScan)
- [ ] Each round: leaderboard updates with correct PnL
- [ ] Each round: broadcast_callback called with trade data
- [ ] `tick()` triggers one immediate round
- [ ] `add_agent_mid_season()` → new agent trades in next round
- [ ] Season completes after N rounds, winner declared
- [ ] All trades have hedera_tx_id (or None with logged error)
- [ ] Verify a tx_id on HashScan → shows HTS transfer
- [ ] Verify HCS price topic on HashScan → shows timestamped prices
- [ ] Verify HCS reasoning topic on HashScan → shows agent decision + reasoning

---

## Phase 9: FastAPI Backend (45 min)

### 9.1 `engine/api/websocket.py`

**`WSManager` class:**
- `connections: set[WebSocket]`
- `async connect(ws)` — add to set
- `async disconnect(ws)` — remove from set
- `async broadcast(data: dict)` — send to all, catch per-connection exceptions, auto-remove dead clients

### 9.2 `engine/api/routes.py`

All REST endpoints from PRD:
- `POST /api/agents/create` — calls factory.create_agent(), adds to orchestrator mid-season
- `POST /api/allocate` — calls hedera.allocate_capital() → real ARENA transfer to agent wallet
- `GET /api/agents/templates` — returns 4 preset thesis strings
- `GET /api/league` — season status + leaderboard from DB
- `GET /api/agents` — all agents with current stats
- `GET /api/agents/{id}` — agent profile + last 10 trades
- `GET /api/agents/{id}/trades` — paginated trades
- `POST /api/season/start` — starts a season
- `POST /api/season/tick` — manual round trigger (demo control)
- `GET /api/feed` — last 20 trades across all agents
- `POST /api/allocate` — real ARENA transfer from treasury → agent wallet (hedera.allocate_capital)

### 9.3 `engine/api/app.py`

- FastAPI app with CORS (allow all origins for hackathon)
- On startup: init DB, init HederaClient, init MarketFeed, init Orchestrator, warmup LLM
- Mount routes + WebSocket endpoint at `/ws/live`
- Orchestrator's broadcast_callback = WSManager.broadcast

### 9.4 `engine/main.py`
```python
uvicorn.run("engine.api.app:app", host="0.0.0.0", port=8000, reload=True)
```

### 9.5 Verify
- [ ] `uvicorn` starts without errors
- [ ] `GET /api/agents/templates` returns 4 theses
- [ ] `POST /api/agents/create` with thesis → creates agent, returns profile
- [ ] `POST /api/season/start` → rounds begin running
- [ ] `GET /api/league` shows leaderboard updating
- [ ] `GET /api/feed` shows trades with reasoning
- [ ] WebSocket at `/ws/live` receives trade broadcasts
- [ ] `POST /api/season/tick` triggers one round immediately
- [ ] Creating an agent mid-season → agent starts trading next round

---

## Phase 10: End-to-End Smoke Test (30 min)

### The Full Run
1. Start the server: `python -m engine.main`
2. Create 4 preset agents: `python -m engine.scripts.seed_presets`
3. Start a season: `curl -X POST localhost:8000/api/season/start`
4. Watch trades appear: `curl localhost:8000/api/feed`
5. Check leaderboard: `curl localhost:8000/api/league`
6. Create a new agent mid-season:
   ```
   curl -X POST localhost:8000/api/agents/create \
     -H "Content-Type: application/json" \
     -d '{"thesis": "All in on ETH dips. Never touch DOGE."}'
   ```
7. Force a round: `curl -X POST localhost:8000/api/season/tick`
8. Verify new agent traded: `curl localhost:8000/api/feed`
9. Allocate capital to an agent:
   ```
   curl -X POST localhost:8000/api/allocate \
     -H "Content-Type: application/json" \
     -d '{"agent_id": "ethmxi-xxx", "amount": 1000}'
   ```
10. **On-chain verification (the triple check):**
    - Pick a trade → check HTS transfer tx_id on HashScan
    - Check HCS Price Oracle topic on HashScan → see timestamped price messages
    - Check HCS Trade Reasoning topic on HashScan → see agent decision + reasoning
    - Check allocation → ARENA transfer visible on agent's account
11. Connect WebSocket client → verify live broadcasts

### Success Criteria
- [ ] 4+ agents trading autonomously
- [ ] Each agent's reasoning is unique and matches its thesis
- [ ] Leaderboard ranks correctly by composite score
- [ ] Real HTS transactions on HashScan
- [ ] HCS Price Oracle topic has a message per round with prices
- [ ] HCS Trade Reasoning topic has a message per trade with reasoning
- [ ] Capital allocation sends real ARENA to agent wallet
- [ ] New agent created mid-season participates immediately
- [ ] WebSocket broadcasts trade data in real-time
- [ ] Season completes, winner declared
- [ ] No crashes, no hangs, no nonce errors

---

## Build Order Summary

| Phase | What | Time | Depends On |
|-------|------|------|-----------|
| 0 | Scaffolding + deps | 30 min | Nothing |
| 1 | Schemas + LLM client | 45 min | Phase 0 |
| 2 | Price feed | 30 min | Phase 0 |
| 3 | Database layer | 30 min | Phase 0 |
| 4 | Portfolio tracker | 45 min | Phase 1, 3 |
| 5 | Scoring system | 30 min | Phase 3 |
| 6 | Hedera client (HTS + HCS + wallets) | 2h | Phase 0 |
| 7 | Agent base + factory | 45 min | Phase 1, 3, 6 |
| 8 | Orchestrator (with HCS publishing) | 1h | Phase 2, 4, 5, 6, 7 |
| 9 | FastAPI backend (with allocation) | 45 min | Phase 3, 7, 8 |
| 10 | E2E smoke test (triple on-chain verify) | 30 min | Phase 9 |
| **TOTAL** | | **~8.5h** | |

### Parallelizable Work
Phases 1, 2, 3 can be done simultaneously (no deps on each other).
Phase 6 (Hedera) is the critical path and the riskiest — start it early, interleave with others.

### If Hedera Blocks
Everything still works with `hedera_tx_id = None` and HCS publishing skipped. The agents trade, the leaderboard updates, reasoning is stored in SQLite. You just lose the on-chain proof. Add Hedera back once the blocker is resolved — the integration points are isolated in `hedera_client.py`.

### The Critical Path
```
Phase 0 → Phase 6 (Hedera) → Phase 7 (Agent factory) → Phase 8 (Orchestrator) → Phase 9 (API) → Phase 10 (E2E)
```

Everything else feeds into the orchestrator. If Hedera blocks, the rest still works with `hedera_tx_id = None` in trade records.
