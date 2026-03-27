"use client"

import React, { useState } from "react"
import Link from "next/link"
import type { Agent } from "@/lib/api"
import { allocateCapital, fetchUserBalance } from "@/lib/api"
import { toast } from "sonner"
// No card wrappers — flush edge-to-edge

function formatPnl(pnl: number | null | undefined): string {
  if (pnl == null || typeof pnl !== "number" || isNaN(pnl)) return "—"
  const sign = pnl >= 0 ? "+" : ""
  return `${sign}${pnl.toFixed(1)}%`
}

function pnlColor(pnl: number | null | undefined): string {
  if (pnl == null || typeof pnl !== "number" || isNaN(pnl)) return "text-white/30"
  return pnl >= 0 ? "text-green-400" : "text-red-400"
}

export function Leaderboard({
  agents,
  selectedAgentId,
  onSelectAgent,
  onBalanceUpdate,
}: {
  agents: Agent[]
  selectedAgentId: string | null
  onSelectAgent: (id: string | null) => void
  onBalanceUpdate?: (newBalance: number) => void
}) {
  const sorted = [...agents].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999))
  const [allocatingId, setAllocatingId] = useState<string | null>(null)
  const [allocAmount, setAllocAmount] = useState("1000")
  const [allocLoading, setAllocLoading] = useState(false)

  async function handleAllocate(agentId: string) {
    const userId = localStorage.getItem("alphaarena_user_id")
    if (!userId) { toast.error("Create an account first"); return }
    const amount = parseInt(allocAmount)
    if (isNaN(amount) || amount <= 0) { toast.error("Enter a valid amount"); return }
    setAllocLoading(true)
    try {
      await allocateCapital(userId, agentId, amount)
      toast.success(`Allocated ${amount.toLocaleString()} aUSD on-chain`)
      setAllocatingId(null)
      setAllocAmount("1000")
      // Refresh balance in parent
      if (onBalanceUpdate) {
        const data = await fetchUserBalance(userId)
        onBalanceUpdate(data.arena_balance)
      }
    } catch { toast.error("Allocation failed. Check your balance.") }
    finally { setAllocLoading(false) }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-2 border-b border-[#1a1a1a]/50">
        <h3 className="text-xs uppercase tracking-widest text-[#c9a84c]/60" style={{ fontFamily: "var(--font-poppins)" }}>Leaderboard</h3>
      </div>
      <div className="flex-1 overflow-y-auto overflow-x-hidden thin-scrollbar">
        {sorted.length === 0 ? (
          <p className="text-xs text-white/30 text-center py-8 px-4">
            No agents yet. Create one to start.
          </p>
        ) : (
          <table className="w-full text-left table-fixed">
            <thead>
              <tr className="text-[10px] text-white/25 uppercase tracking-widest border-b border-[#1a1a1a]/50 sticky top-0 bg-[#080808] z-10">
                <th className="px-4 py-2 font-normal w-7 text-left">#</th>
                <th className="px-2 py-2 font-normal text-left">Agent</th>
                <th className="px-2 py-2 font-normal text-left">P&L</th>
                <th className="px-2 py-2 font-normal text-left">Balance</th>
                <th className="px-2 py-2 font-normal text-left hidden sm:table-cell">Backed</th>
                <th className="px-2 py-2 font-normal text-left hidden sm:table-cell">WR</th>
                <th className="px-4 py-2 font-normal text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((agent) => {
                const isSelected = selectedAgentId === agent.id
                return (
                  <React.Fragment key={agent.id}>
                    <tr
                      onClick={() => onSelectAgent(isSelected ? null : agent.id)}
                      className={`cursor-pointer transition-colors border-b border-[#1a1a1a]/50 ${
                        isSelected
                          ? "bg-[#c9a84c]/5"
                          : "hover:bg-white/[0.02]"
                      }`}
                    >
                      <td className="px-4 py-2.5">
                        <span className={`text-[11px] font-mono ${
                          agent.rank === 1 ? "text-[#c9a84c]" :
                          agent.rank === 2 ? "text-white/60" :
                          agent.rank === 3 ? "text-amber-700" :
                          "text-white/20"
                        }`}>
                          {agent.rank ?? "—"}
                        </span>
                      </td>
                      <td className="px-2 py-2.5 max-w-[90px]">
                        <span className="text-[13px] text-white/90 block truncate">{agent.name}</span>
                      </td>
                      <td className="px-2 py-2.5">
                        <span className={`text-[13px] font-mono ${pnlColor(agent.pnl_pct)}`}>
                          {formatPnl(agent.pnl_pct)}
                        </span>
                      </td>
                      <td className="px-2 py-2.5">
                        <span className="text-[11px] text-white/30 font-mono">
                          {((agent as any).portfolio_value != null ? `$${((agent as any).portfolio_value as number).toLocaleString(undefined, {maximumFractionDigits: 0})}` : `$${(10000 * (1 + (agent.pnl_pct ?? 0) / 100)).toLocaleString(undefined, {maximumFractionDigits: 0})}`)}
                        </span>
                      </td>
                      <td className="px-2 py-2.5 hidden sm:table-cell">
                        <span className="text-[11px] text-white/30 font-mono">
                          {((agent as any).total_backed != null ? `$${((agent as any).total_backed as number).toLocaleString(undefined, {maximumFractionDigits: 0})}` : "—")}
                        </span>
                      </td>
                      <td className="px-2 py-2.5 hidden sm:table-cell">
                        <span className="text-[11px] text-white/30 font-mono">
                          {agent.win_rate != null ? `${agent.win_rate.toFixed(0)}%` : "—"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <div className="relative group/back">
                            <button
                              onClick={(e) => { e.stopPropagation(); setAllocatingId(allocatingId === agent.id ? null : agent.id) }}
                              className="w-7 h-7 flex items-center justify-center rounded-md text-green-400/40 hover:text-green-400 hover:bg-green-400/10 transition-all cursor-pointer"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                            </button>
                            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 text-[10px] text-white/80 bg-[#1a1a1a] rounded whitespace-nowrap opacity-0 group-hover/back:opacity-100 transition-opacity pointer-events-none z-50">Back Agent</span>
                          </div>
                          <div className="relative group/view">
                            <Link
                              href={`/agent/${agent.id}`}
                              onClick={(e) => e.stopPropagation()}
                              className="w-7 h-7 flex items-center justify-center rounded-md text-[#c9a84c]/40 hover:text-[#c9a84c] hover:bg-[#c9a84c]/10 transition-all"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                            </Link>
                            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 text-[10px] text-white/80 bg-[#1a1a1a] rounded whitespace-nowrap opacity-0 group-hover/view:opacity-100 transition-opacity pointer-events-none z-50">View Agent</span>
                          </div>
                        </div>
                      </td>
                    </tr>
                    {allocatingId === agent.id && (
                      <tr key={`${agent.id}-alloc`} className="bg-green-400/[0.02]">
                        <td colSpan={7} className="px-4 py-2">
                          <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="number"
                              value={allocAmount}
                              onChange={(e) => setAllocAmount(e.target.value)}
                              className="w-24 bg-black border border-[#1a1a1a] rounded px-2 py-1 text-xs text-white/80 focus:outline-none focus:border-green-400/30"
                              placeholder="Amount"
                            />
                            <span className="text-[10px] text-white/30">aUSD</span>
                            <button
                              onClick={() => handleAllocate(agent.id)}
                              disabled={allocLoading}
                              className="text-[10px] bg-green-400/10 text-green-400 border border-green-400/20 rounded px-2 py-1 hover:bg-green-400/20 transition-colors cursor-pointer disabled:opacity-30"
                            >
                              {allocLoading ? "..." : "Send"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
