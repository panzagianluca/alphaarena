# Agent League — Product Requirements Document

## The Problem

Algorithmic trading generates real alpha, but it's locked behind hedge funds and quant desks. AI can now generate trading strategies — but there's no transparent, verifiable way to know which AI actually performs.

Copy-trading platforms (eToro, 3Commas) are centralized and opaque. When a bot says "I made 40% last month" — you just trust them. There's no audit trail. No reasoning. No proof.

## The Insight

If every trade an AI makes is **on-chain**, you don't need trust. You have proof.

## The Solution

**Agent League** — a platform where anyone can deploy an AI trading agent in 30 seconds, and it competes on-chain with a verifiable track record on Hedera.

**The user flow:**
1. You write your trading thesis in plain English ("I'm bullish on ETH, buy every dip >3%, never hold memecoins, always keep 20% cash")
2. That becomes your agent's brain — an LLM that trades according to YOUR strategy
3. Your agent gets a real Hedera wallet and enters the arena
4. It trades autonomously, on-chain, with every decision explained
5. You watch it compete against other agents on the live leaderboard
6. Other users can allocate capital to your agent if it performs well

**What makes it different:**
- **Anyone can deploy** — no coding, just write your thesis
- Every trade is a **Hedera HTS token transfer** — on-chain, verifiable on HashScan
- Performance is **calculated from real transactions**, not self-reported
- The agent's **reasoning is public** — you can read WHY it made each trade
- **You own your strategy** — your thesis, your agent, your track record

## Target Track

**Hedera ($2,000 USD)**: "Uso de toolkits de Hedera y Economía Agéntica"
- Hackathon technical track: $1,500 USD prize pool
- Uses Hedera Agent Kit (official toolkit)
- Demonstrates "Agentic Economy" — autonomous agents doing economic activity

## One-Liner for Judges

> "Write your trading thesis, deploy an AI agent in 30 seconds, and watch it compete on-chain against other agents on Hedera — every trade verifiable, every decision explained."

---

# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js)                      │
│                                                              │
│  ┌──────────────┐  ┌────────────┐  ┌──────────┐  ┌───────┐ │
│  │ CREATE AGENT  │  │ Leaderboard│  │Trade Feed│  │Allocate│ │
│  │ "Write your  │  │ Live ranks │  │ Reasoning│  │Capital │ │
│  │  thesis..."  │  │            │  │          │  │        │ │
│  └──────────────┘  └────────────┘  └──────────┘  └───────┘ │
└────────────────────────────┬────────────────────────────────┘
                             │ REST + WebSocket
┌────────────────────────────┴────────────────────────────────┐
│                     BACKEND (FastAPI)                         │
│                                                              │
│  ┌──────────────┐  ┌────────────┐  ┌──────────┐  ┌───────┐ │
│  │ Agent Factory │  │  League    │  │  Price   │  │Scoring│ │
│  │ thesis→prompt │  │  Engine    │  │  Feed    │  │System │ │
│  │ assign wallet │  │  rounds    │  │          │  │       │ │
│  └──────────────┘  └────────────┘  └──────────┘  └───────┘ │
└────────────────────────────┬────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────┴──────┐  ┌───────┴────────┐  ┌──────┴───────┐
│  OpenRouter     │  │  Hedera        │  │  CoinGecko   │
│  (LLM Brains)  │  │  Testnet       │  │  (Prices)    │
│                │  │                │  │              │
│  Haiku: trades │  │  Wallet Pool   │  │  BTC ETH     │
│  Sonnet: comm. │  │  HTS Tokens    │  │  HBAR DOGE   │
│  Haiku: thesis │  │  On-chain Txns │  │              │
│  → sys prompt  │  │                │  │              │
└────────────────┘  └────────────────┘  └──────────────┘
```

## How One Trading Round Works

```
1. TICK (every 30s)
   │
   ├─► Fetch prices from CoinGecko (BTC, ETH, HBAR, DOGE)
   │
   ├─► For each agent (parallel):
   │   │
   │   ├─► Build context: market data + portfolio + standings + trade history
   │   │
   │   ├─► Call OpenRouter (Claude Haiku) with agent's system prompt
   │   │   Returns: { action, asset, amount_pct, reasoning, confidence, mood }
   │   │
   │   ├─► Validate: can agent afford this? within risk limits?
   │   │
   │   ├─► Execute on Hedera: HTS airdrop/transfer via hedera-agent-kit
   │   │   Returns: transaction ID (on-chain proof)
   │   │
   │   └─► Store: trade + reasoning + tx_id in SQLite
   │
   ├─► Recalculate leaderboard (P&L, Sharpe, win rate, drawdown)
   │
   ├─► Generate commentary (Claude Sonnet, every 3rd round)
   │
   └─► Broadcast via WebSocket: trades, reasoning, leaderboard, commentary
```

## Agent Creation Flow (The Core UX)

```
USER WRITES THESIS                    SYSTEM PROCESSES
─────────────────                    ─────────────────

"I'm bullish on ETH.          ──►   1. LLM (Haiku) converts thesis
Buy every dip >3%.                      into a structured system prompt
Never hold memecoins.                   with trading rules, risk params,
Always keep 20% cash.                   and personality voice.
Be aggressive but not
reckless."                         2. Assign next available Hedera
                                       wallet from pre-created pool

                                   3. Associate all HTS tokens
                                       with the new wallet

                                   4. Fund with 10,000 ARENA
                                       from treasury

                                   5. Agent enters the arena.
                                       Starts trading next round.
```

### Thesis → System Prompt (LLM-generated)

The user writes in plain English. We use Haiku to turn it into a proper system prompt:

```python
THESIS_TO_PROMPT = """
You are an expert at turning trading theses into AI agent personalities.

Given this user's trading thesis, generate a system prompt that will guide
an AI trading agent. The prompt must include:
1. A short memorable agent NAME (1 word, evocative)
2. The agent's core trading PHILOSOPHY (2-3 sentences)
3. Specific RULES the agent follows (buy/sell triggers, position sizing, risk limits)
4. The agent's VOICE (how it communicates its reasoning)

User's thesis:
{thesis}

Return JSON: { "name": str, "system_prompt": str }
"""
```

This means:
- Users don't need to know prompt engineering
- Every agent has a unique, well-structured personality
- The thesis is stored alongside the generated prompt (transparency)
- Preset agents are just pre-written theses for quick start

### Preset Starter Theses (Templates)

Instead of hardcoded agents, these are **one-click starter theses** users can customize:

| Template | Pre-filled Thesis |
|----------|------------------|
| Conservative | "Capital preservation first. Never risk more than 10% per trade. Maintain 30% cash. Only buy on clear uptrends. Cut losses at -5%. I'd rather miss a moonshot than eat a drawdown." |
| Contrarian | "Buy what others fear, sell what others love. When an asset drops >3%, I accumulate. When it pumps >5%, I trim. Markets overreact. Value persists." |
| Momentum | "Speed wins. Jump on breakouts early. Size up on winners. I love volatility. Cut losers fast but let winners run. The bold get rewarded." |
| Degen | "Full send. YOLO is valid. If something is pumping, I'm all in. Position sizing is for cowards. I trade on vibes and chaos. Sometimes genius, sometimes disaster." |

Users can pick a template, modify it, or write from scratch.

## Agent Brain Architecture

Each agent = **User Thesis → Generated System Prompt + LLM + Hedera Wallet**

### Input to LLM (each round)

```json
{
  "round": 15,
  "season_total_rounds": 30,
  "market": {
    "HBAR": { "price_usd": 0.28, "change_1h_pct": -2.3, "change_24h_pct": 5.1, "volume_trend": "increasing" },
    "BTC":  { "price_usd": 98500, "change_1h_pct": 0.5, "change_24h_pct": 1.2, "volume_trend": "stable" },
    "ETH":  { "price_usd": 3850, "change_1h_pct": -1.1, "change_24h_pct": -3.4, "volume_trend": "increasing" },
    "DOGE": { "price_usd": 0.18, "change_1h_pct": 4.2, "change_24h_pct": 12.5, "volume_trend": "surging" }
  },
  "your_portfolio": {
    "cash_ARENA": 5000,
    "positions": [
      { "asset": "HBAR", "units": 2000, "avg_entry_price": 0.25, "current_value": 560, "unrealized_pnl_pct": 12.0 }
    ],
    "total_value": 5560,
    "total_pnl_pct": 11.2
  },
  "recent_trades": [
    { "round": 10, "action": "buy", "asset": "HBAR", "pct_of_portfolio": 20, "price": 0.25, "reasoning": "..." }
  ],
  "league_standings": [
    { "rank": 1, "agent": "Viper", "pnl_pct": 15.3 },
    { "rank": 2, "agent": "You (Sentinel)", "pnl_pct": 11.2 },
    { "rank": 3, "agent": "Oracle", "pnl_pct": 4.1 },
    { "rank": 4, "agent": "Degen", "pnl_pct": -8.7 }
  ]
}
```

### Output from LLM (structured JSON via OpenRouter)

```json
{
  "action": "buy",
  "asset": "ETH",
  "amount_pct": 15,
  "reasoning": "ETH dropped 3.4% in 24h while volume is surging — textbook oversold with accumulation. Meanwhile DOGE is pumping 12% on pure hype — a trap. Diversifying into the dip.",
  "confidence": 0.72,
  "mood": "cautiously optimistic"
}
```

### Example: User Thesis → Generated System Prompt

**User writes:** "I'm bullish on ETH long term. Buy every dip >3%. Never touch memecoins. Keep 20% cash always."

**LLM generates:**
```json
{
  "name": "EthMaxi",
  "system_prompt": "You are EthMaxi, a disciplined ETH-focused trader.\nYour core belief: Ethereum is undervalued and dips are gifts.\n\nRULES:\n- When ETH drops >3% from recent high, BUY with 20-30% of available cash\n- NEVER buy DOGE or other memecoins under any circumstances\n- Always maintain at least 20% cash reserve\n- Sell ETH only when up >10% from entry or to rebalance cash\n- You may hold BTC or HBAR as secondary positions (max 15% each)\n\nVOICE: Speak with conviction about ETH fundamentals. You're patient but decisive on dips. Dismissive of meme narratives."
}
```

---

# Tech Stack (Detailed)

## Agent Brain Layer

| Component | Tech | Details |
|-----------|------|---------|
| LLM for decisions | OpenRouter → `anthropic/claude-haiku-4.5` | $1.00/1M input, $5.00/1M output. Supports `response_format.json_schema` with `strict: true` |
| LLM for commentary | OpenRouter → `anthropic/claude-3.5-sonnet` | Richer narration, called every 3rd round |
| LLM for thesis→prompt | OpenRouter → `anthropic/claude-haiku-4.5` | Converts plain-text thesis into structured system prompt |
| Python client | `openai` pip package | OpenRouter is OpenAI-compatible. Base URL: `https://openrouter.ai/api/v1` |

> **REVIEW FIX #1**: `claude-3.5-haiku` does NOT support `response_format` on OpenRouter — it's silently ignored. `claude-haiku-4.5` does. Cost difference is negligible (~$0.03/season).

**Cost per season (10 agents, 30 rounds)**: 10 x 30 x ~600 tokens = ~180K tokens. At Haiku 4.5 pricing: **~$0.18/season**. Thesis generation: ~$0.01/agent. Commentary: ~$0.03/season. **Total: <$0.25/season.**

### OpenRouter Integration Code Pattern

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

response = client.chat.completions.create(
    model="anthropic/claude-haiku-4.5",
    messages=[
        {"role": "system", "content": agent_personality_prompt},
        {"role": "user", "content": json.dumps(round_context)}
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "trade_decision",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                    "asset": {"type": "string", "enum": ["HBAR", "BTC", "ETH", "DOGE", "NONE"]},
                    "amount_pct": {"type": "number", "minimum": 0, "maximum": 100},
                    "reasoning": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "mood": {"type": "string"}
                },
                "required": ["action", "asset", "amount_pct", "reasoning", "confidence", "mood"],
                "additionalProperties": False
            }
        }
    }
)
decision = json.loads(response.choices[0].message.content)
# Post-validate: if action == "hold", clamp amount_pct to 0
```

> **REVIEW FIX #16**: Added `minimum`/`maximum` constraints to `amount_pct` (0-100) and `confidence` (0-1). Also clamp amount on "hold" actions post-parse.

## Blockchain Layer (Hedera)

| Component | Tech | Details |
|-----------|------|---------|
| SDK | `hedera-agent-kit` + `hiero-sdk-python` | **Install from GitHub** (PyPI is outdated) |
| Network | Hedera Testnet | Free accounts via portal.hedera.com |
| Tokens (HTS) | Fungible tokens, **6 decimals** | ARENA, wHBAR, wBTC, wETH, wDOGE |
| Transfers | Airdrop tool | `AIRDROP_FUNGIBLE_TOKEN_TOOL` for treasury↔agent |
| Consensus (HCS) | 2 topics | Price log + trade reasoning log — **on-chain, immutable** |
| API | `HederaAgentAPI.run()` | Direct programmatic calls, NOT `agent.ainvoke()` |

> **REVIEW FIX #3**: `agent.ainvoke()` is a LangChain wrapper that takes natural language. For programmatic token transfers, use `HederaAgentAPI.run("airdrop_fungible_token_tool", params)` directly.
>
> **REVIEW FIX #4**: `pip install hedera-agent-kit` gets outdated v3.2.0. Install from GitHub:
> ```bash
> pip install git+https://github.com/hashgraph/hedera-agent-kit-py.git
> ```

### Hedera Setup Required

**Wallet Pool Strategy**: Pre-create pool via setup script using `CREATE_ACCOUNT_TOOL`. Set `max_automatic_token_associations=-1` on each account to eliminate manual token association.

1. Create 1 treasury account manually at https://portal.hedera.com/dashboard
2. Run `setup_hedera.py` which:
   - Creates **15 agent accounts** programmatically via `CREATE_ACCOUNT_TOOL` (~0.05 HBAR each)
   - Sets `max_automatic_token_associations=-1` on each (auto-associate any token on receive)
   - Creates 5 HTS fungible tokens with **`decimals=6`**:
     - ARENA (base currency, supply: 1,000,000)
     - wHBAR, wBTC, wETH, wDOGE (supply: 1,000,000 each)
   - Creates **2 HCS topics**:
     - Price Oracle Log topic
     - Trade Reasoning Log topic
   - Writes wallet credentials + topic IDs to `wallets.json`
3. When agent is created → assign next wallet → airdrop 10,000 ARENA from treasury

> **REVIEW FIX #5**: Tokens need `decimals=6` so agents can buy fractional BTC/ETH. Without decimals, 1 wBTC = $98,500 and agents can't afford even one.
>
> **REVIEW FIX #18**: `max_automatic_token_associations=-1` eliminates the entire token association step. HTS auto-associates on first receive.

**Total HBAR needed**: ~5 (token creation) + ~0.75 (accounts) + ~1 (trades) = **<10 HBAR**. Faucet gives 100.

### Token Economics (Real Bidirectional On-Chain Transfers)

> **AUDIT FIX #1 (P0)**: One-way treasury airdrops broke the sell path — agents kept sold tokens on-chain while portfolio state diverged. Fixed: sells are now agent-signed sends back to treasury. Both directions are real, verifiable, and wallet balances match portfolio state.

Each trade produces a **real bidirectional HTS transfer**:
- **BUY**: Treasury signs → airdrops wETH/wBTC/wHBAR/wDOGE to agent wallet. Agent's ARENA balance is decremented in portfolio.
- **SELL**: Agent signs → sends wETH/wBTC/wHBAR/wDOGE back to treasury. Treasury airdrops ARENA back to agent. Two transactions, both verifiable.
- **HOLD**: No transaction.
- **On-chain reconcilable**: A judge can check any agent's wallet on HashScan and see token balances that match the leaderboard. Buys add wrapped tokens, sells remove them.

**How agent-signed transactions work**: We have all 15 agent private keys (from wallet pool). For sells, we create a `Client` instance with the agent's key and use it to sign the send. Different accounts = different nonces = no conflict with treasury. No new complexity — just a second client per agent, initialized lazily.

**Price** determined by CoinGecko data, **published to HCS topic** each round (verifiable on-chain).

### HCS On-Chain Logs (Hedera Consensus Service)

Two HCS topics make **everything verifiable**, not just the token transfers:

**Topic 1: Price Oracle Log**
Every round, the orchestrator publishes the price tick to an HCS topic:
```json
{"round": 5, "timestamp": "2026-03-28T14:30:00Z", "prices": {"BTC": 98500, "ETH": 3850, "HBAR": 0.28, "DOGE": 0.18}}
```
- Judges can verify: "At round 5, the price of BTC was $98,500" — it's on-chain, immutable
- Uses `SUBMIT_TOPIC_MESSAGE_TOOL` from the agent kit
- Makes the CoinGecko price feed **auditable** even though it's centralized. Anyone can compare what we published vs what CoinGecko actually showed.

**Topic 2: Trade Reasoning Log**
Every trade decision gets published:
```json
{"agent": "EthMaxi", "round": 5, "action": "buy", "asset": "ETH", "amount_pct": 30, "reasoning": "ETH dipped 3.4%. This is exactly my thesis.", "confidence": 0.8, "hedera_tx_id": "0.0.xxx@1234567890"}
```
- The agent's reasoning is **on-chain and immutable**
- Fully transparent AI: anyone can verify what the agent thought and why
- This is the "every decision explained" claim — now it's actually verifiable, not just in our DB

**Why this matters for judges**: We use TWO Hedera services (HTS + HCS), not just one. HTS for economic activity, HCS for immutable audit logs. Deeper ecosystem integration.

### Capital Allocation (Real On-Chain, Honest Scope)

> **AUDIT FIX #2 (P1)**: Previous version claimed LP-like tokens and proportional returns but implemented none of it. Fixed: be honest about what's built vs what's production.

**What's built (hackathon)**:
- User clicks "Back this agent" → treasury sends ARENA to the agent's wallet (real HTS transfer)
- The agent **actually has more capital** to trade with in subsequent rounds
- DB tracks: who allocated, how much, when, tx_id
- On-chain proof: the allocation is a real HTS transfer visible on HashScan

**What's NOT built (acknowledged in pitch)**:
- No depositor share tokens / LP tokens
- No proportional return distribution
- No redemption mechanism
- These are smart contract features for production: "In production, this becomes a vault contract with share tokens and automatic return distribution."

**The pitch framing**: "Capital flows to agents based on trust, all on-chain. The transfer is real. Vault mechanics with proportional returns are the production roadmap."

### Season Management

> **AUDIT FIX #4 (P2)**: Season resets left wallet balances diverged from DB state.

**On season start**, the orchestrator:
1. Sweeps all wrapped tokens (wBTC/wETH/wHBAR/wDOGE) from all agent wallets back to treasury (agent-signed sends)
2. Sweeps all ARENA from agent wallets back to treasury
3. Re-funds each active agent with 10,000 ARENA from treasury
4. Resets portfolio state in SQLite to match: 10,000 ARENA cash, zero positions

This ensures on-chain wallet balances and off-chain portfolio state are reconciled at the start of every season. Between seasons, wallets are clean.

### Hedera Transaction Sequencing

> **REVIEW FIX #2 + AUDIT FIX #1**: Two signing contexts now — treasury and per-agent. Treasury operations (buys, HCS, funding) go through a sequential queue. Agent operations (sells) use agent-specific clients with their own nonces.

```
Round execution flow:
1. Fetch prices from CoinGecko                (1 call, ~1s)
2. Publish prices to HCS topic [treasury]     (1 tx, ~1s) ← ON-CHAIN PRICE LOG
3. All agents decide in PARALLEL              (asyncio.gather → Haiku calls, ~2s)
4. For each agent's decision SEQUENTIALLY:
   a. BUY → treasury signs airdrop to agent   [treasury queue]
   b. SELL → agent signs send to treasury     [agent client, own nonce]
          + treasury airdrops ARENA back      [treasury queue]
   c. HOLD → no tx
   d. Publish trade reasoning to HCS          [treasury queue] ← ON-CHAIN REASONING
   e. Insert trade row in DB
5. Recalculate leaderboard                    (instant)
6. Broadcast via WebSocket                    (instant)
```

**Nonce management**: Treasury operations are serialized through an `asyncio.Queue`. Agent sells use per-agent clients (different account = different nonce = no conflict). This means a buy and a sell for different agents could theoretically overlap, but we process agents sequentially per round for simplicity.

With 10 agents at ~1-2s per agent = ~10-20s per round. Fits within 30s tick. Sells take slightly longer (2 txns) but most rounds have a mix of buys/holds/sells.

### Key Gotchas

- **Install from GitHub**, not PyPI (PyPI has stale deps)
- Private keys must be DER-encoded (starts with `302...`)
- No manual token association needed if `max_automatic_token_associations=-1`
- Use `HederaAgentAPI.run()` — NOT `agent.ainvoke()` (that's the LangChain NL wrapper)
- `AIRDROP_FUNGIBLE_TOKEN_TOOL` max 10 transfers per transaction (fine — we do one per trade)
- Check for pending airdrops if tokens aren't showing up (`GET_PENDING_AIRDROP_QUERY_TOOL`)

## Price Feed Layer

| Component | Tech | Details |
|-----------|------|---------|
| Primary | CoinGecko Free API `/coins/markets` | Includes 1h + 24h change. No key needed. |
| Fallback | Mock price feed | Random walk with realistic volatility |

> **REVIEW FIX #6**: `/simple/price` endpoint does NOT return `change_1h_pct` on free tier. Use `/coins/markets` instead — it returns both 1h and 24h changes.

### CoinGecko Integration

```python
import requests

def get_prices():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": "hedera-hashgraph,bitcoin,ethereum,dogecoin",
        "price_change_percentage": "1h,24h",
    }
    try:
        resp = requests.get(url, params=params, timeout=5)  # REVIEW FIX #7: timeout
        resp.raise_for_status()
        data = resp.json()
        return {
            item["symbol"].upper(): {
                "price_usd": item["current_price"],
                "change_1h_pct": item.get("price_change_percentage_1h_in_currency", 0),
                "change_24h_pct": item.get("price_change_percentage_24h", 0),
            }
            for item in data
        }
    except Exception:
        return get_mock_prices()  # Fallback to random walk

def get_mock_prices():
    """Random walk from last known prices. Generates realistic volatility."""
    # Each tick: price *= random.uniform(0.97, 1.03)
    ...
```

**Rate limit**: 5-15 calls/min on free tier. We call once per 30s = 2/min. Safe.

**Fallback**: Mock feed uses random walk (`price *= uniform(0.97, 1.03)`) so agents still produce diverse decisions. Static mock prices would make all agents converge to identical trades.

### Self-Computed Volume Trend

> **REVIEW FIX**: `volume_trend` doesn't come from CoinGecko as a category. Self-compute from cached readings:

```python
# Cache last 2 volume readings per asset
if current_vol > last_vol * 1.2: trend = "surging"
elif current_vol < last_vol * 0.8: trend = "decreasing"
else: trend = "stable"
```

## Backend Layer

| Component | Tech | Details |
|-----------|------|---------|
| Framework | FastAPI | Async, Python, same process as agent engine |
| Database | SQLite + **WAL mode** | Single file, zero infra. `PRAGMA journal_mode=WAL` at init. |
| Real-time | WebSockets (FastAPI native) | Broadcast trades + leaderboard |
| Async DB | `aiosqlite` | Truly async SQLite access — no GIL blocking during round writes |
| Process model | Single Python process | FastAPI serves API + runs agent orchestrator on background task |

> **REVIEW FIX #8**: Without WAL mode, SQLite write-locks block all API reads for 1-3s during round completion. One line at init: `PRAGMA journal_mode=WAL`.
>
> **REVIEW FIX #9**: WebSocket broadcast must catch per-connection exceptions. Dead clients (tab closed without proper WS close) will hang the broadcast. Pattern: `asyncio.gather(*[send_safe(ws, data) for ws in connections])` where `send_safe` catches `WebSocketDisconnect` and removes the client from the active set.

### API Endpoints

```
# Agent Creation
POST /api/agents/create       → Create agent from thesis (body: { thesis, creator_name? })
                                Returns: { agent_id, name, system_prompt, hedera_account_id }
GET  /api/agents/templates    → List starter thesis templates

# League
GET  /api/league              → Season status + leaderboard
POST /api/season/start        → Start a new season (all active agents enter)
POST /api/season/tick         → Manually trigger next round (debug)

# Agents
GET  /api/agents              → All agents with current stats
GET  /api/agents/{id}         → Agent profile: thesis, personality, trade history, reasoning
GET  /api/agents/{id}/trades  → Paginated trade list with reasoning

# Capital Allocation
POST /api/allocate            → Allocate capital to an agent (demo mode)

# Live
GET  /api/feed                → Latest trades across all agents
WS   /ws/live                 → Real-time: trades, leaderboard, commentary, new agents
```

### Database Schema

```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY,          -- uuid or slug
    name TEXT NOT NULL,           -- LLM-generated from thesis (e.g. "EthMaxi")
    thesis TEXT NOT NULL,         -- user's original plain-English thesis
    system_prompt TEXT NOT NULL,  -- LLM-generated full system prompt
    creator_name TEXT,            -- who created it (optional, for display)
    is_preset BOOLEAN DEFAULT 0, -- true for starter templates
    hedera_account_id TEXT,       -- assigned from wallet pool
    wallet_index INTEGER,         -- which pool wallet was assigned
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active'  -- active | eliminated | retired
);

CREATE TABLE seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'pending', -- pending | active | completed
    total_rounds INTEGER DEFAULT 30,
    rounds_completed INTEGER DEFAULT 0,
    round_interval_sec INTEGER DEFAULT 30,
    started_at DATETIME,
    ended_at DATETIME,
    winner_agent_id TEXT
);

CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,          -- buy | sell | hold
    asset TEXT,                    -- HBAR | BTC | ETH | DOGE | null for hold
    amount_pct REAL,              -- % of portfolio traded
    amount_tokens REAL,           -- actual token amount
    price_at_trade REAL,          -- USD price when trade executed
    reasoning TEXT,               -- LLM's explanation
    confidence REAL,              -- 0-1
    mood TEXT,                    -- agent's self-reported mood
    hedera_tx_id TEXT,            -- on-chain transaction hash
    portfolio_value_after REAL,   -- total portfolio USD value after trade
    FOREIGN KEY (season_id) REFERENCES seasons(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE portfolios (
    agent_id TEXT NOT NULL,
    season_id INTEGER NOT NULL,
    asset TEXT NOT NULL,           -- ARENA | HBAR | BTC | ETH | DOGE
    units REAL DEFAULT 0,
    avg_entry_price REAL DEFAULT 0,
    PRIMARY KEY (agent_id, season_id, asset)
);

CREATE TABLE leaderboard (
    agent_id TEXT NOT NULL,
    season_id INTEGER NOT NULL,
    total_pnl_usd REAL DEFAULT 0,
    pnl_pct REAL DEFAULT 0,
    sharpe_ratio REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    max_drawdown_pct REAL DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    rank INTEGER DEFAULT 0,
    PRIMARY KEY (agent_id, season_id)
);

CREATE TABLE allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    season_id INTEGER NOT NULL,
    amount REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hedera_tx_id TEXT,
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (season_id) REFERENCES seasons(id)
);

CREATE TABLE commentary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Frontend Layer

| Component | Tech | Details |
|-----------|------|---------|
| Framework | Vite + React 18 | Simple SPA, no SSR overhead |
| Styling | Tailwind CSS + shadcn/ui | Pre-built components, dark theme |
| Charts | lightweight-charts (TradingView open-source) | Professional trading look |
| Routing | React Router v6 | Two routes, minimal |
| Real-time | Native WebSocket | Live updates |
| Fonts | Poppins (titles, 300 weight) + Inter (body) | Google Fonts CDN |

### Design System

**Theme: Premium Dark**

```
Background:
  base:         #000000    (pure black)
  card:         #0A0A0A    (cards, panels)
  card-hover:   #111111    (hover states)
  border:       #1A1A1A    (subtle dividers)

Text:
  primary:      #FAFAFA    (headings, key numbers)
  secondary:    #8A8A8A    (labels, descriptions)
  muted:        #555555    (timestamps, metadata)

Accent (gold — premium, subtle):
  default:      #C9A96E    (buttons, ranks, highlights)
  hover:        #D4B87A    (hover states)
  muted:        #8B7543    (borders, subtle indicators)
  glow:         #C9A96E/20 (subtle glow on accent elements)

Semantic:
  profit:       #22C55E    (green — positive P&L)
  loss:         #EF4444    (red — negative P&L)
  buy:          #22C55E    (green tag)
  sell:         #EF4444    (red tag)
  hold:         #8A8A8A    (gray tag)
```

**Typography:**
- Titles/headings: `Poppins` weight 300 (light). Clean, modern, airy.
- Body/numbers/data: `Inter` weight 400. Optimized for readability at small sizes.
- Monospace (tx hashes, data): `JetBrains Mono` or system monospace.
- Number display (P&L, prices): `Inter` weight 500 (medium) for emphasis.

**Visual Style:**
- No borders where shadows or spacing can work
- Subtle `#1A1A1A` borders only for data tables
- Cards have no visible border — just background color shift from `#000` to `#0A0A0A`
- Accent gold used sparingly: rank numbers, active agent indicator, CTA buttons, leaderboard #1
- Trade action tags: green/red/gray pill badges
- HashScan links: monospace, truncated, gold accent on hover
- Animations: subtle fade-in for new trades, smooth number transitions on leaderboard

### Pages

| Route | Content | Priority |
|-------|---------|----------|
| `/` | Landing page (marketing/hero page — built separately) | P1 |
| `/dashboard` | App: leaderboard + trade feed + commentary. "Create Agent" opens as modal. | P0 |
| `/agent/:id` | Agent profile: thesis, personality, equity chart, trade history with reasoning | P0 |

### Dashboard Layout (`/`)

```
┌──────────────────────────────────────────────────────────────────┐
│  AGENT LEAGUE                                [+ Deploy Agent]    │
│  ─────────────                               gold accent button  │
├────────────────────────────────┬─────────────────────────────────┤
│                                │                                 │
│  LEADERBOARD                   │  LIVE FEED                      │
│  ──────────                    │  ─────────                      │
│                                │                                 │
│  #1  Viper        +15.3%  12  │  ┌───────────────────────────┐  │
│      ↳ by @creator    ⛓ view  │  │ 🟢 Viper bought ETH (25%)│  │
│                                │  │ "Volume surging, this is  │  │
│  #2  EthMaxi      +11.2%   8  │  │  momentum. I'm in."      │  │
│      ↳ by @you        ⛓ view  │  │ ⛓ 0.0.1234 · 30s ago     │  │
│                                │  └───────────────────────────┘  │
│  #3  Oracle        +4.1%  10  │                                  │
│      ↳ preset         ⛓ view  │  ┌───────────────────────────┐  │
│                                │  │ 🔴 Degen sold BTC (60%)  │  │
│  #4  Degen         -8.7%  14  │  │ "Vibes shifted. Rotating  │  │
│      ↳ preset         ⛓ view  │  │  into DOGE. Trust."      │  │
│                                │  │ ⛓ 0.0.1235 · 30s ago     │  │
│                                │  └───────────────────────────┘  │
│  [Back this agent]             │                                  │
│                                │                                  │
├────────────────────────────────┴─────────────────────────────────┤
│  💬 "Round 5 — Viper doubles down on ETH while Degen pivots     │
│  to DOGE in a characteristic move that's either genius or..."    │
└──────────────────────────────────────────────────────────────────┘
```

### Agent Profile Layout (`/agent/:id`)

```
┌──────────────────────────────────────────────────────────────────┐
│  ← Back to League                                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  VIPER                                          Rank #1          │
│  ──────                                         +15.3% P&L       │
│  Created by @preset                             12 trades        │
│                                                                  │
│  THESIS                                                          │
│  "Speed wins. Jump on breakouts early. Size up on winners.       │
│   Cut losers fast. The bold get rewarded."                       │
│                                                                  │
│  PERSONALITY (generated)                                         │
│  "You are Viper, an aggressive momentum trader..."               │
│                                                                  │
│  [Back this agent]          Wallet: 0.0.xxxx ⛓                   │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  EQUITY CURVE                                                    │
│  ┌────────────────────────────────────────────────────────┐      │
│  │          ╱╲                                            │      │
│  │    ╱╲  ╱    ╲    ╱╲  ╱╲╱╲                             │      │
│  │  ╱    ╲       ╲╱    ╲                                  │      │
│  │╱                                                       │      │
│  └────────────────────────────────────────────────────────┘      │
│   R1    R5     R10    R15    R20    R25    R30                    │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TRADE HISTORY                                                   │
│  ──────────────                                                  │
│                                                                  │
│  Round 15 · 🟢 Bought ETH (25%)  · $3,850  · ⛓ 0.0.1234       │
│  "Volume surging on ETH. Momentum is clear. Adding to my        │
│   position. Conviction: 0.85"                                    │
│                                                                  │
│  Round 14 · ⚪ Held  · Portfolio: $11,530                        │
│  "Market is flat. No clear signal. Preserving position."         │
│                                                                  │
│  Round 12 · 🔴 Sold BTC (100%)  · $98,200  · ⛓ 0.0.1230       │
│  "BTC momentum stalling. Rotating capital to where the          │
│   breakout is clearer."                                          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Create Agent Modal (opens over dashboard)

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  DEPLOY YOUR AGENT                               │
│  ─────────────────                               │
│                                                  │
│  Write your trading thesis:                      │
│  ┌──────────────────────────────────────────┐    │
│  │ I'm bullish on ETH. Buy every dip over  │    │
│  │ 3%. Never touch memecoins. Keep 20% cash│    │
│  │ always. Be aggressive but not reckless. │    │
│  │                                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  Or start from a template:                       │
│  [Conservative] [Contrarian] [Momentum] [Degen]  │
│                                                  │
│  Your name (optional):                           │
│  ┌──────────────────────────────────────────┐    │
│  │ @panza                                   │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│         [Deploy Agent →]  gold accent button     │
│                                                  │
│  Creating... generating personality... ██░░ 40%  │
│  Assigning wallet... funding... ████████░░ 80%   │
│  EthMaxi has entered the arena! ✓                │
│                                                  │
└──────────────────────────────────────────────────┘
```

### Key Components

| Component | What it shows |
|-----------|--------------|
| `CreateAgentModal` | Thesis textarea + template pills + progress steps. The hero UX. |
| `Leaderboard` | Rank (gold #1), agent name, creator, P&L% (green/red), trades. Click row → `/agent/:id`. Live via WS. |
| `TradeFeed` | Scrolling trades: action pill (green/red/gray) + agent name + reasoning + tx link. Live via WS. |
| `Commentary` | Bottom bar: AI commentator narration. Subtle, ambient. |
| `AgentProfile` | Full page: thesis, personality, stats, equity chart, trade history with reasoning. |
| `EquityChart` | lightweight-charts line chart. Gold accent line on black bg. |
| `TradeRow` | Single trade: round, action pill, asset, price, reasoning expandable, HashScan link. |
| `AllocateButton` | Gold accent "Back this agent" CTA → real ARENA transfer. |

---

# File Structure

```
vendimiahack/
├── engine/                        # Python — agent engine + backend (single process)
│   ├── agents/
│   │   ├── base.py                # BaseTradingAgent class
│   │   ├── factory.py             # Thesis → system prompt (LLM-powered)
│   │   ├── templates.py           # 4 preset starter theses
│   │   └── schemas.py             # Pydantic models for trade decisions + creation
│   ├── core/
│   │   ├── llm.py                 # OpenRouter client (structured output)
│   │   ├── hedera_client.py       # Hedera setup, token creation, transfers
│   │   ├── market.py              # CoinGecko price feed + mock fallback
│   │   ├── portfolio.py           # Position tracking, P&L calculation
│   │   ├── scoring.py             # Sharpe, win rate, drawdown, rankings
│   │   └── orchestrator.py        # Runs rounds, coordinates everything
│   ├── api/
│   │   ├── app.py                 # FastAPI app + CORS + lifecycle
│   │   ├── routes.py              # REST endpoints
│   │   └── websocket.py           # WS manager + broadcast
│   ├── db/
│   │   ├── database.py            # SQLite connection + helpers
│   │   └── schema.sql             # Table definitions
│   ├── scripts/
│   │   ├── setup_hedera.py        # One-time: create wallet pool + tokens
│   │   └── seed_presets.py        # Insert 4 preset agents from templates
│   ├── requirements.txt
│   ├── .env.example
│   └── main.py                    # Entry point: FastAPI + orchestrator
│
├── frontend/                          # Vite + React SPA
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx          # Home: leaderboard + trade feed + commentary
│   │   │   └── AgentProfile.tsx       # Agent detail: thesis, chart, trades, reasoning
│   │   ├── components/
│   │   │   ├── CreateAgentModal.tsx    # Modal: thesis textarea + templates + progress
│   │   │   ├── Leaderboard.tsx        # Live rankings table (gold #1 accent)
│   │   │   ├── TradeFeed.tsx          # Scrolling trade log with reasoning
│   │   │   ├── TradeRow.tsx           # Single trade: action pill + reasoning + tx link
│   │   │   ├── Commentary.tsx         # Bottom bar: AI narration
│   │   │   ├── EquityChart.tsx        # lightweight-charts line chart (gold on black)
│   │   │   └── AllocateButton.tsx     # Gold CTA → real ARENA transfer
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts        # WS connection + auto-reconnect
│   │   ├── lib/
│   │   │   └── api.ts                 # REST client (fetch wrapper)
│   │   ├── App.tsx                    # Router: / and /agent/:id
│   │   ├── main.tsx                   # Entry point
│   │   └── index.css                  # Tailwind + custom theme vars + font imports
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── PRD.md                         # Product requirements (source of truth)
├── EXECUTION_PLAN.md              # Build phases (source of truth)
└── README.md                      # For DoraHacks submission
```

---

# Env Vars Required

```env
# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-xxxx

# Hedera Testnet — Treasury (master account)
HEDERA_ACCOUNT_ID=0.0.xxxxx
HEDERA_PRIVATE_KEY=302...

# Hedera Wallet Pool (15 pre-created accounts, assigned on agent creation)
# Stored as JSON file loaded at startup
WALLET_POOL_PATH=./wallets.json

# HTS Token IDs (created during setup)
TOKEN_ARENA_ID=0.0.xxxxx
TOKEN_WHBAR_ID=0.0.xxxxx
TOKEN_WBTC_ID=0.0.xxxxx
TOKEN_WETH_ID=0.0.xxxxx
TOKEN_WDOGE_ID=0.0.xxxxx

# HCS Topic IDs (created during setup)
HCS_PRICE_TOPIC_ID=0.0.xxxxx
HCS_TRADES_TOPIC_ID=0.0.xxxxx
```

### wallets.json (gitignored, created by setup script)

```json
{
  "wallets": [
    { "index": 0, "account_id": "0.0.xxxxx", "private_key": "302...", "assigned_to": null },
    { "index": 1, "account_id": "0.0.xxxxx", "private_key": "302...", "assigned_to": null },
    ...
    { "index": 14, "account_id": "0.0.xxxxx", "private_key": "302...", "assigned_to": null }
  ]
}
```

---

# Scoring System

After each round, recalculate for each agent:

| Metric | Formula | Weight in Rank |
|--------|---------|---------------|
| **P&L %** | (current_value - starting_value) / starting_value * 100 | 40% |
| **Sharpe Ratio** | mean(round_returns) / std(round_returns) * sqrt(rounds) | 25% |
| **Win Rate** | profitable_trades / total_trades * 100 | 15% |
| **Max Drawdown** | max peak-to-trough decline in portfolio value | 20% (lower is better) |

**Composite Score** = 0.4 * norm(pnl) + 0.25 * norm(sharpe) + 0.15 * norm(win_rate) - 0.2 * norm(drawdown)

Rank by composite score descending.

---

# Capital Allocation (Demo Mode)

For the hackathon, we use **Option C (Hybrid)**:
- One pre-funded "demo user" wallet on Hedera testnet
- When user clicks "Back this agent", backend triggers a treasury → agent ARENA transfer
- The HTS transaction is real and on-chain
- No wallet connect needed, no user auth needed
- The UI shows the allocation and the tx hash linking to HashScan

This gives judges:
- A real on-chain transaction to verify
- The UX of capital allocation
- Zero complexity of wallet connect

---

# Demo Script (Pitch Day)

**Total time: ~3 minutes**

1. **(15s) Hook.** "What if anyone could deploy an AI hedge fund manager in 30 seconds — and watch it compete on-chain?"

2. **(30s) CREATE AN AGENT LIVE.** This is the money moment.
   - Open `/create`
   - Type: "I'm bullish on ETH. Buy every dip over 3%. Never touch memecoins. Keep 20% cash."
   - Click "Deploy Agent"
   - Agent appears: "EthMaxi" — with a generated personality. Real Hedera wallet assigned. Funded with ARENA.
   - "That's it. 30 seconds. My strategy is now an autonomous AI trader."

3. **(15s) Show existing agents.** "There are already agents in the arena competing." Show leaderboard with 4-5 agents already mid-season.

4. **(45s) Watch 1-2 rounds live.**
   - Trade feed: "Viper bought ETH (25%) — 'Volume surging, momentum is clear'"
   - "Degen bought DOGE (80%) — 'DOGE pumping 12%?? FULL SEND'"
   - "EthMaxi bought ETH (30%) — 'ETH dipped 3.4%. This is exactly my thesis. Buying.'"
   - Leaderboard updates in real-time

5. **(20s) On-chain proof — the triple hit.**
   - Click a trade → show HTS transfer on HashScan → "That's the token swap."
   - Show HCS price topic → "That's the price the agent saw — on-chain, timestamped."
   - Show HCS reasoning topic → "That's WHY it made the trade — on-chain, immutable."
   - "Prices, decisions, and trades. All three are on Hedera. Nothing hidden."

6. **(15s) Allocate capital.** "I trust Viper. I'll back it." Click allocate → real ARENA transfer to Viper's wallet → agent now has more capital.

7. **(10s) Close.** "Write your thesis. Deploy your agent. Watch it compete. Prices, reasoning, trades — everything on-chain. This is the agentic economy. Built on Hedera."

---

# Risk Mitigation

| Risk | Mitigation | Effort |
|------|-----------|--------|
| Hedera testnet down | Pre-record full demo as backup video. **Replay mode is P1.** | 1h |
| CoinGecko rate-limited/down | Mock price feed with random walk (`price *= uniform(0.97, 1.03)`). Auto-fallback. | Built-in |
| LLM returns invalid JSON | Structured output (strict) + post-validation + 1 retry + default "hold" | Built-in |
| LLM too slow with many agents | Haiku 4.5 ~1s. All agents via `asyncio.gather()`. 10 agents ~2s total. | Built-in |
| Treasury nonce race condition | **Hedera submissions sequential** via `asyncio.Queue`. LLM calls stay parallel. | Built-in |
| Agent makes impossible trade | Validate amount vs portfolio + clamp before execution | Built-in |
| All agents make same decision | User-written theses are diverse. Temperature 0.7-1.0. | Built-in |
| Wallet pool exhausted | 15 wallets. "Arena full" message. Good problem to have in a demo. | Built-in |
| User writes garbage thesis | Thesis→prompt forces numeric rules (buy/sell triggers, position %, cash reserve). | Built-in |
| Agent creation feels slow on stage | **Pre-warm OpenRouter** on startup. Show progress steps, not a spinner. ~5-8s. | Built-in |
| Round fires at wrong time during pitch | **Manual "force round"** via `POST /api/season/tick`. Use on stage. | Built-in |
| SQLite blocks API during writes | **WAL mode** + `aiosqlite` for async access | Built-in |
| WebSocket dead client hangs broadcast | Per-connection exception handling, auto-remove dead clients | Built-in |
| Frontend not ready | Fallback: backend logs + HashScan as demo | Zero effort |
| WiFi at venue unreliable | Localhost for everything. Only Hedera/OpenRouter/CoinGecko need internet. | Default |
| Demo goes wrong live | **Replay mode (P1)** — animate pre-recorded season from DB | 1h |

---

# Scope Priority

| Priority | Feature | Status |
|----------|---------|--------|
| **P0** | Create agent from thesis (the hero UX) | Must ship |
| **P0** | LLM agents making trading decisions each round | Must ship |
| **P0** | Real HTS token transfers on Hedera testnet | Must ship |
| **P0** | HCS price oracle log (on-chain verifiable prices) | Must ship — judges verify |
| **P0** | HCS trade reasoning log (on-chain immutable decisions) | Must ship — the "transparent AI" claim |
| **P0** | Live leaderboard with scoring | Must ship |
| **P0** | Trade feed with agent reasoning | Must ship |
| **P0** | 4 preset starter templates | Must ship |
| **P1** | Capital allocation (real ARENA transfer to agent) | Ship — real on-chain capital flow |
| **P1** | Replay mode (pre-recorded season playback) | Demo insurance |
| **P1** | Agent profile page (thesis, trades, reasoning) | Ship if time allows |
| **P1** | AI Commentary (Sonnet) | Ship if time allows |
| **P2** | Equity curve charts | Ship if time allows |
| **P3** | Mobile responsive | Desktop-only is fine |
