"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { fetchAgent, fetchAgentTrades, fetchPortfolioHistory, type Agent, type Trade } from "@/lib/api"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"

function timeAgo(ts: string): string {
  const normalized = ts.includes("T") ? ts : ts.replace(" ", "T") + "Z"
  const diff = Date.now() - new Date(normalized).getTime()
  const secs = Math.max(0, Math.round(diff / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  return `${Math.round(mins / 60)}h ago`
}

function actionColor(action: string): string {
  if (action === "buy") return "text-green-400"
  if (action === "sell") return "text-red-400"
  return "text-white/40"
}

function pnlColor(pnl: number | null): string {
  if (pnl === null) return "text-white/30"
  return pnl >= 0 ? "text-green-400" : "text-red-400"
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="space-y-0.5">
      <span className="text-[10px] uppercase tracking-widest text-white/30">{label}</span>
      <p className={`text-sm font-medium font-mono ${color || "text-white/80"}`}>{value}</p>
    </div>
  )
}

export default function AgentProfile() {
  const params = useParams()
  const id = params.id as string
  const [agent, setAgent] = useState<Agent | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [equityData, setEquityData] = useState<{ round: number; value: number }[]>([])
  const [allocations, setAllocations] = useState<Array<{ amount: number; timestamp: string; hedera_tx_id: string; user_id: string }>>([])
  const [totalBacked, setTotalBacked] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [agentData, tradesData, portfolioHistory] = await Promise.all([
        fetchAgent(id),
        fetchAgentTrades(id, 50),
        fetchPortfolioHistory(),
      ])
      if (agentData) {
        setAgent(agentData.agent)
        setTrades(agentData.trades?.length ? agentData.trades : tradesData)

        // Filter portfolio history for this agent
        const agentName = agentData.agent.name
        if (portfolioHistory && Array.isArray(portfolioHistory)) {
          const filtered = portfolioHistory
            .filter((snap: Record<string, number>) => agentName in snap)
            .map((snap: Record<string, number>) => ({ round: snap.round, value: snap[agentName] }))
          setEquityData(filtered)
        }
      }

      // Fetch allocations for this agent
      try {
        const res = await fetch(`${API_BASE}/api/agents/${id}/allocations`)
        if (res.ok) {
          const data = await res.json()
          setAllocations(data.allocations || [])
          setTotalBacked(data.total_backed || 0)
        }
      } catch { /* ignore */ }

      setLoading(false)
    }
    load()
  }, [id])

  if (loading) {
    return (
      <div className="h-screen bg-black flex items-center justify-center">
        <p className="text-sm text-white/30 animate-pulse">Loading agent...</p>
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="h-screen bg-black flex items-center justify-center flex-col gap-4">
        <p className="text-sm text-white/40">Agent not found</p>
        <Link href="/dashboard" className="text-[#c9a84c] text-sm hover:underline">
          ← Back to Dashboard
        </Link>
      </div>
    )
  }

  const pnlPct = agent.pnl_pct
  const pnlSign = pnlPct != null && pnlPct >= 0 ? "+" : ""

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <div className="border-b border-[#1a1a1a] px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="text-white/30 hover:text-white/60 transition-colors text-sm">
            ← Back
          </Link>
          <div className="w-px h-5 bg-[#1a1a1a]" />
          <div className="flex items-center gap-3">
            {agent.rank && (
              <span className="w-7 h-7 rounded-full border border-[#c9a84c]/30 bg-[#c9a84c]/10 flex items-center justify-center text-[11px] text-[#c9a84c] font-medium">
                #{agent.rank}
              </span>
            )}
            <h1
              className="text-xl font-light text-white/90"
              style={{ fontFamily: "var(--font-poppins)" }}
            >
              {agent.name}
            </h1>
            {agent.is_preset ? (
              <span className="text-[9px] text-white/20 uppercase tracking-wider border border-[#1a1a1a] px-2 py-0.5 rounded-full">Preset</span>
            ) : (
              <span className="text-[9px] text-[#c9a84c]/50 uppercase tracking-wider border border-[#c9a84c]/20 px-2 py-0.5 rounded-full">Custom</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={`text-lg font-mono font-medium ${pnlColor(pnlPct)}`}>
            {pnlPct != null ? `${pnlSign}${pnlPct.toFixed(1)}%` : "—"}
          </span>
        </div>
      </div>

      <div className="p-5 space-y-4 max-w-6xl mx-auto overflow-y-auto thin-scrollbar">
        {/* Stats Row */}
        <Card>
          <CardHeader>
            <CardTitle>Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
              <Stat
                label="P&L"
                value={pnlPct != null ? `${pnlSign}${pnlPct.toFixed(2)}%` : "—"}
                color={pnlColor(pnlPct)}
              />
              <Stat label="Trades" value={`${agent.total_trades ?? 0}`} />
              <Stat label="Sharpe" value={agent.sharpe_ratio?.toFixed(2) ?? "—"} />
              <Stat label="Win Rate" value={agent.win_rate != null ? `${agent.win_rate.toFixed(0)}%` : "—"} />
              <Stat label="Max DD" value={agent.max_drawdown_pct != null ? `${agent.max_drawdown_pct.toFixed(1)}%` : "—"} color="text-red-400" />
            </div>
          </CardContent>
        </Card>

        {/* Equity Curve */}
        <Card>
          <CardHeader>
            <CardTitle>Equity Curve</CardTitle>
          </CardHeader>
          <CardContent>
            {equityData.length === 0 ? (
              <p className="text-xs text-white/30 text-center py-8">No chart data yet</p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={equityData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                  <defs>
                    <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#c9a84c" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#c9a84c" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1a1a1a" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="round"
                    tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                    axisLine={{ stroke: "#1a1a1a" }}
                    tickLine={{ stroke: "#1a1a1a" }}
                    tickFormatter={(v: number) => `${Math.round(v)}`}
                  />
                  <YAxis
                    domain={[
                      (dataMin: number) => Math.floor(dataMin - Math.max((dataMin * 0.005), 10)),
                      (dataMax: number) => Math.ceil(dataMax + Math.max((dataMax * 0.005), 10)),
                    ]}
                    allowDataOverflow
                    tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                    axisLine={{ stroke: "#1a1a1a" }}
                    tickLine={{ stroke: "#1a1a1a" }}
                    tickFormatter={(v: number) =>
                      v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v}`
                    }
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0a0a0a",
                      border: "1px solid #1a1a1a",
                      borderRadius: "8px",
                      fontSize: "12px",
                      color: "rgba(255,255,255,0.8)",
                    }}
                    labelStyle={{ color: "rgba(255,255,255,0.5)" }}
                    formatter={(value: number) => [`$${value.toLocaleString()}`, "Portfolio"]}
                    labelFormatter={(label: number) => `Update ${label}`}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#c9a84c"
                    strokeWidth={2}
                    fill="url(#equityGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Two columns: Thesis + Info | System Prompt */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Thesis</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-white/60 leading-relaxed">{agent.thesis}</p>
              <div className="mt-4 pt-3 border-t border-[#1a1a1a] flex items-center gap-4 text-[10px] text-white/25">
                <span>Created by {agent.creator_name || "Anonymous"}</span>
                <span>{new Date(agent.created_at).toLocaleDateString()}</span>
                <span className="font-mono">{agent.hedera_account_id}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>AI Personality</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-[12px] text-white/40 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto thin-scrollbar">
                {agent.system_prompt}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Allocations / Backers */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Backers</CardTitle>
              <span className="text-sm font-mono" style={{ color: "#c9a84c" }}>
                {totalBacked.toLocaleString()} aUSD total
              </span>
            </div>
          </CardHeader>
          <CardContent>
            {allocations.length === 0 ? (
              <p className="text-xs text-white/30 text-center py-4">
                No one has backed this agent yet. Be the first from the dashboard.
              </p>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto thin-scrollbar">
                {allocations.map((al, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-2 border-b border-[#1a1a1a]/50 last:border-0"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-mono" style={{ color: "#c9a84c" }}>
                        {al.amount.toLocaleString()} aUSD
                      </span>
                      <span className="text-[10px] text-white/20">
                        by {(al as Record<string, unknown>).backer_name as string || "Anonymous"}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] text-white/20">{timeAgo(al.timestamp)}</span>
                      {al.hedera_tx_id && (
                        <a
                          href={`https://hashscan.io/testnet/transaction/${al.hedera_tx_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-[#c9a84c]/40 hover:text-[#c9a84c] transition-colors"
                        >
                          ⛓ verify
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Trade History */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Trade History</CardTitle>
              <span className="text-[10px] text-white/25">{trades.length} trades</span>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {trades.length === 0 ? (
              <p className="text-xs text-white/30 text-center py-8 px-4">
                No trades yet. This agent hasn&apos;t participated in a season.
              </p>
            ) : (
              <div className="max-h-[50vh] overflow-y-auto thin-scrollbar">
                {/* Header */}
                <div className="grid grid-cols-7 gap-2 px-4 py-2 text-[10px] text-white/25 uppercase tracking-widest border-b border-[#1a1a1a] sticky top-0 bg-[#0a0a0a]">
                  <span>Trade #</span>
                  <span>Action</span>
                  <span>Asset</span>
                  <span>Size</span>
                  <span>Portfolio</span>
                  <span>Reasoning</span>
                  <span>Verify</span>
                </div>

                {trades.map((trade) => (
                  <div
                    key={trade.id}
                    className="grid grid-cols-7 gap-2 px-4 py-2.5 border-b border-[#1a1a1a]/50 text-xs hover:bg-white/[0.02] transition-colors"
                  >
                    <span className="text-white/30 font-mono">#{trade.round_number}</span>
                    <span className={`font-medium uppercase ${actionColor(trade.action)}`}>
                      {trade.action}
                    </span>
                    <span className="text-white/60 font-mono">{trade.asset || "—"}</span>
                    <span className="text-white/40 font-mono">{trade.amount_pct}%</span>
                    <span className="text-white/50 font-mono">${trade.portfolio_value_after?.toFixed(0) ?? "—"}</span>
                    <span className="text-white/30 truncate" title={trade.reasoning}>
                      {trade.reasoning}
                    </span>
                    <span>
                      {trade.hedera_tx_id ? (
                        <a
                          href={`https://hashscan.io/testnet/transaction/${trade.hedera_tx_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[#c9a84c]/50 hover:text-[#c9a84c] transition-colors font-mono"
                        >
                          ⛓ verify
                        </a>
                      ) : (
                        <span className="text-white/15">—</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
