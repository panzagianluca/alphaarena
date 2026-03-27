"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { fetchUserPortfolio, claimFaucet, type Agent } from "@/lib/api"

function timeAgo(ts: string | undefined): string {
  if (!ts) return ""
  const normalized = ts.includes("T") ? ts : ts.replace(" ", "T") + "Z"
  const diff = Date.now() - new Date(normalized).getTime()
  const secs = Math.max(0, Math.round(diff / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  return `${Math.round(mins / 60)}h ago`
}

export function PortfolioModal({
  isOpen,
  onClose,
  userId,
  onBalanceUpdate,
}: {
  isOpen: boolean
  onClose: () => void
  userId: string
  onBalanceUpdate: (newBalance: number) => void
}) {
  const [balance, setBalance] = useState<number>(0)
  const [agentsCreated, setAgentsCreated] = useState<Agent[]>([])
  const [allocations, setAllocations] = useState<Array<{ agent_name: string; amount: number; timestamp: string; hedera_tx_id: string; agent_id: string }>>([])
  const [loading, setLoading] = useState(true)
  const [claiming, setClaiming] = useState(false)
  const [claimMsg, setClaimMsg] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen && userId) {
      setLoading(true)
      fetchUserPortfolio(userId).then((data) => {
        setBalance(data?.balance ?? 0)
        setAgentsCreated(data?.agents_created ?? [])
        setAllocations(data?.allocations ?? [])
        setLoading(false)
      }).catch(() => setLoading(false))
    }
  }, [isOpen, userId])

  async function handleClaim() {
    setClaiming(true)
    setClaimMsg(null)
    try {
      const result = await claimFaucet(userId)
      setBalance(result.arena_balance)
      onBalanceUpdate(result.arena_balance)
      setClaimMsg(`+10,000 aUSD claimed!`)
    } catch {
      setClaimMsg("Faucet limit reached (max 3 claims)")
    }
    setClaiming(false)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl w-full max-w-md mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1a1a1a]">
          <h2
            className="text-lg font-light text-white/90"
            style={{ fontFamily: "var(--font-poppins)" }}
          >
            My Portfolio
          </h2>
          <button
            onClick={onClose}
            className="text-white/30 hover:text-white/60 transition-colors text-lg cursor-pointer"
          >
            ✕
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <p className="text-sm text-white/30 animate-pulse">Loading...</p>
          </div>
        ) : (
          <div className="overflow-y-auto thin-scrollbar flex-1 px-5 py-4 space-y-5">
            {/* Balance */}
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase tracking-widest text-white/30">Balance</span>
                <p className="text-xl font-mono font-medium" style={{ color: "#c9a84c" }}>
                  {(balance ?? 0).toLocaleString()} <span className="text-sm text-[#c9a84c]/60">aUSD</span>
                </p>
              </div>
              <button
                onClick={handleClaim}
                disabled={claiming}
                className="text-[11px] border border-[#c9a84c]/30 text-[#c9a84c] px-3 py-1.5 rounded-full hover:bg-[#c9a84c]/10 transition-all cursor-pointer disabled:opacity-50"
              >
                {claiming ? "Claiming..." : "+ Get aUSD"}
              </button>
            </div>
            {claimMsg && (
              <p className={`text-[11px] ${claimMsg.includes("+") ? "text-green-400" : "text-red-400"}`}>
                {claimMsg}
              </p>
            )}

            {/* My Agents */}
            <div>
              <span className="text-[10px] uppercase tracking-widest text-white/30">My Agents</span>
              {agentsCreated.length === 0 ? (
                <p className="text-xs text-white/20 mt-2">No agents created yet</p>
              ) : (
                <div className="mt-2 space-y-2">
                  {agentsCreated.map((a) => (
                    <Link
                      key={a.id}
                      href={`/agent/${a.id}`}
                      onClick={onClose}
                      className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-[#1a1a1a] hover:border-[#c9a84c]/20 transition-all"
                    >
                      <div className="flex items-center gap-3">
                        {a.rank && (
                          <span className="text-[10px] text-[#c9a84c]/60 font-mono">#{a.rank}</span>
                        )}
                        <span className="text-sm text-white/80">{a.name}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`text-xs font-mono ${
                          a.pnl_pct != null ? (a.pnl_pct >= 0 ? "text-green-400" : "text-red-400") : "text-white/20"
                        }`}>
                          {a.pnl_pct != null ? `${a.pnl_pct >= 0 ? "+" : ""}${a.pnl_pct.toFixed(1)}%` : "—"}
                        </span>
                        <span className="text-[10px] text-white/20">{a.total_trades || 0} trades</span>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* My Allocations */}
            <div>
              <span className="text-[10px] uppercase tracking-widest text-white/30">My Allocations</span>
              {allocations.length === 0 ? (
                <p className="text-xs text-white/20 mt-2">No allocations yet. Back an agent from the leaderboard.</p>
              ) : (
                <div className="mt-2 space-y-2">
                  {allocations.map((al, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-[#1a1a1a]"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono" style={{ color: "#c9a84c" }}>
                          {al.amount.toLocaleString()}
                        </span>
                        <span className="text-[10px] text-white/30">aUSD →</span>
                        <Link
                          href={`/agent/${al.agent_id}`}
                          onClick={onClose}
                          className="text-sm text-white/80 hover:text-[#c9a84c] transition-colors"
                        >
                          {al.agent_name}
                        </Link>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-white/20">{timeAgo(al.timestamp)}</span>
                        {al.hedera_tx_id && (
                          <a
                            href={`https://hashscan.io/testnet/transaction/${al.hedera_tx_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[10px] text-[#c9a84c]/40 hover:text-[#c9a84c]"
                          >
                            ⛓
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}