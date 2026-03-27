const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export interface Agent {
  id: string
  name: string
  thesis: string
  system_prompt: string
  creator_name: string
  is_preset: number
  hedera_account_id: string
  wallet_index: number
  created_at: string
  status: string
  total_pnl_usd: number | null
  pnl_pct: number | null
  sharpe_ratio: number | null
  win_rate: number | null
  max_drawdown_pct: number | null
  total_trades: number | null
  rank: number | null
}

export interface Trade {
  id: number
  agent_id: string
  agent_name?: string
  round_number: number
  timestamp: string
  action: string
  asset: string
  amount_pct: number
  amount_tokens: number
  price_at_trade: number
  reasoning: string
  confidence: number
  mood: string
  hedera_tx_id: string | null
  hcs_tx_id: string | null
  portfolio_value_after: number
}

export interface Season {
  id: number
  status: string
  total_rounds: number
  rounds_completed: number
  round_interval_sec: number
  started_at: string
  ended_at: string | null
  winner_agent_id: string | null
}

export interface LeagueData {
  season: Season | null
  leaderboard: Agent[]
}

export interface AgentTemplate {
  thesis: string
  creator_name: string
  label: string
  description: string
}

async function safeFetch<T>(url: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(url)
    if (!res.ok) return fallback
    return await res.json()
  } catch {
    return fallback
  }
}

export async function fetchAgents(): Promise<Agent[]> {
  return safeFetch(`${API_BASE}/api/agents`, [])
}

export async function fetchLeague(): Promise<LeagueData> {
  return safeFetch(`${API_BASE}/api/league`, { season: null, leaderboard: [] })
}

export async function fetchFeed(): Promise<Trade[]> {
  return safeFetch(`${API_BASE}/api/feed`, [])
}

export async function fetchAgent(id: string): Promise<{ agent: Agent; trades: Trade[] } | null> {
  return safeFetch(`${API_BASE}/api/agents/${id}`, null)
}

export async function fetchAgentTrades(id: string, limit = 50, offset = 0): Promise<Trade[]> {
  return safeFetch(`${API_BASE}/api/agents/${id}/trades?limit=${limit}&offset=${offset}`, [])
}

export async function fetchTemplates(): Promise<Record<string, AgentTemplate>> {
  const res = await fetch(`${API_BASE}/api/agents/templates`)
  return res.json()
}

export async function createAgent(
  thesis: string,
  agentName?: string,
  userId?: string,
  instruments?: string[],
  model?: string,
): Promise<Agent> {
  const res = await fetch(`${API_BASE}/api/agents/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      thesis,
      agent_name: agentName,
      creator_name: typeof window !== "undefined" ? localStorage.getItem("alphaarena_user_name") || undefined : undefined,
      user_id: userId,
      instruments,
      model,
    }),
  })
  return res.json()
}

export async function startSeason(totalRounds = 30, intervalSec = 30): Promise<void> {
  await fetch(`${API_BASE}/api/season/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ total_rounds: totalRounds, interval_sec: intervalSec }),
  })
}

export async function allocateCapital(userId: string, agentId: string, amount: number): Promise<void> {
  await fetch(`${API_BASE}/api/allocate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, agent_id: agentId, amount }),
  })
}

export async function createUserWallet(name?: string): Promise<{ user_id: string; name: string; hedera_account_id: string; arena_balance: number }> {
  const res = await fetch(`${API_BASE}/api/user/wallet`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || "Anonymous" }),
  })
  return res.json()
}

export async function fetchUserBalance(userId: string): Promise<{ arena_balance: number }> {
  return safeFetch(`${API_BASE}/api/user/${userId}/balance`, { arena_balance: 0 })
}

export async function fetchPortfolioHistory(): Promise<Array<Record<string, number>>> {
  return safeFetch(`${API_BASE}/api/portfolio-history`, [])
}

export async function claimFaucet(userId: string): Promise<{ arena_balance: number; hedera_tx_id: string }> {
  const res = await fetch(`${API_BASE}/api/user/${userId}/faucet`, { method: "POST" })
  return res.json()
}

export async function fetchUserPortfolio(userId: string): Promise<{
  balance: number
  agents_created: Agent[]
  allocations: Array<{ agent_name: string; amount: number; timestamp: string; hedera_tx_id: string; agent_id: string }>
}> {
  return safeFetch(`${API_BASE}/api/user/${userId}/portfolio`, { balance: 0, agents_created: [], allocations: [] })
}
