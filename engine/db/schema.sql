-- Agent League Database Schema
-- All tables use CREATE TABLE IF NOT EXISTS for idempotent initialization.

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    thesis TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    creator_name TEXT,
    user_id TEXT,
    is_preset BOOLEAN DEFAULT 0,
    hedera_account_id TEXT,
    wallet_index INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active'  -- active | eliminated | retired
);

CREATE TABLE IF NOT EXISTS seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'pending',  -- pending | active | completed
    total_rounds INTEGER DEFAULT 30,
    rounds_completed INTEGER DEFAULT 0,
    round_interval_sec INTEGER DEFAULT 30,
    started_at DATETIME,
    ended_at DATETIME,
    winner_agent_id TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,            -- buy | sell | hold
    asset TEXT,                      -- HBAR | BTC | ETH | DOGE | null for hold
    amount_pct REAL,                 -- % of portfolio traded
    amount_tokens REAL,              -- actual token amount
    price_at_trade REAL,             -- USD price when trade executed
    reasoning TEXT,                  -- LLM's explanation
    confidence REAL,                 -- 0-1
    mood TEXT,                       -- agent's self-reported mood
    hedera_tx_id TEXT,               -- on-chain HTS transaction hash
    hcs_tx_id TEXT,                  -- on-chain HCS reasoning message tx
    portfolio_value_after REAL,      -- total portfolio USD value after trade
    FOREIGN KEY (season_id) REFERENCES seasons(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS portfolios (
    agent_id TEXT NOT NULL,
    season_id INTEGER NOT NULL,
    asset TEXT NOT NULL,             -- ARENA | HBAR | BTC | ETH | DOGE
    units REAL DEFAULT 0,
    avg_entry_price REAL DEFAULT 0,
    PRIMARY KEY (agent_id, season_id, asset)
);

CREATE TABLE IF NOT EXISTS leaderboard (
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

CREATE TABLE IF NOT EXISTS allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    season_id INTEGER NOT NULL,
    amount REAL,
    user_id TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hedera_tx_id TEXT,
    withdrawn INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (season_id) REFERENCES seasons(id)
);

-- Migration note: if DB already exists, run:
-- ALTER TABLE allocations ADD COLUMN withdrawn INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS tips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent_id TEXT NOT NULL,
    to_agent_id TEXT NOT NULL,
    amount REAL NOT NULL,
    season_id INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hedera_tx_id TEXT,
    FOREIGN KEY (from_agent_id) REFERENCES agents(id),
    FOREIGN KEY (to_agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS commentary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT DEFAULT 'Anonymous',
    hedera_account_id TEXT NOT NULL,
    wallet_index INTEGER NOT NULL,
    arena_balance REAL DEFAULT 50000.0,
    faucet_claims INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
