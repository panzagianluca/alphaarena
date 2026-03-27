"use client"

import type { Trade } from "@/lib/api"

function timeAgo(ts: string | undefined | null): string {
  if (!ts) return "just now"
  // SQLite format: "2026-03-26 19:43:04" — add T and Z for proper parsing
  const normalized = ts.includes("T") ? ts : ts.replace(" ", "T") + "Z"
  const date = new Date(normalized)
  if (isNaN(date.getTime())) return "just now"
  const diff = Date.now() - date.getTime()
  const secs = Math.max(0, Math.round(diff / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  return `${Math.round(mins / 60)}h ago`
}

function ActionBadge({ action }: { action: string }) {
  const lower = action.toLowerCase()
  let classes = "text-[10px] px-1.5 py-0.5 rounded border font-medium uppercase "
  if (lower === "buy") classes += "text-green-400 bg-green-400/10 border-green-400/20"
  else if (lower === "sell") classes += "text-red-400 bg-red-400/10 border-red-400/20"
  else classes += "text-white/40 bg-white/5 border-white/10"
  return <span className={classes}>{action.toUpperCase()}</span>
}

export function TradeFeed({ trades }: { trades: Trade[] }) {
  return (
    <div className="h-full flex flex-col overflow-hidden border-t border-[#1a1a1a]/50">
      <div className="px-4 py-2 border-b border-[#1a1a1a]/50">
        <h3 className="text-xs uppercase tracking-widest text-[#c9a84c]/60" style={{ fontFamily: "var(--font-poppins)" }}>Activity</h3>
      </div>
      {trades.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-white/30">No trades yet. Start a season to begin.</p>
        </div>
      ) : (
      <div className="flex-1 overflow-y-auto thin-scrollbar">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-[#080808] z-10">
            <tr className="border-b border-[#1a1a1a]/50">
              <th className="text-left text-[11px] text-white/30 uppercase font-medium px-4 py-2">Agent</th>
              <th className="text-left text-[11px] text-white/30 uppercase font-medium px-4 py-2">Action</th>
              <th className="text-left text-[11px] text-white/30 uppercase font-medium px-4 py-2">Asset</th>
              <th className="text-left text-[11px] text-white/30 uppercase font-medium px-4 py-2">Amount</th>
              <th className="text-left text-[11px] text-white/30 uppercase font-medium px-4 py-2">Reasoning</th>
              <th className="text-left text-[11px] text-white/30 uppercase font-medium px-4 py-2">Time</th>
              <th className="text-left text-[11px] text-white/30 uppercase font-medium px-4 py-2">Tx</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr
                key={trade.id}
                className="border-b border-[#1a1a1a]/50 hover:bg-white/[0.02] transition-colors"
              >
                <td className="px-4 py-2 text-[13px] text-white font-medium whitespace-nowrap">
                  {trade.agent_name || trade.agent_id}
                </td>
                <td className="px-4 py-2">
                  <ActionBadge action={trade.action} />
                </td>
                <td className="px-4 py-2 text-[13px] text-white/80 font-mono">
                  {trade.action.toLowerCase() === "hold" ? "—" : trade.asset || "—"}
                </td>
                <td className="px-4 py-2 text-[13px] text-white/80 font-mono">
                  {trade.amount_pct != null ? `${trade.amount_pct}%` : "—"}
                </td>
                <td className="px-4 py-2 text-[13px] text-white/40 italic max-w-[300px] truncate">
                  {trade.reasoning
                    ? trade.reasoning.length > 60
                      ? trade.reasoning.slice(0, 60) + "…"
                      : trade.reasoning
                    : "—"}
                </td>
                <td className="px-4 py-2 text-[13px] text-white/50 whitespace-nowrap">
                  {timeAgo(trade.timestamp)}
                </td>
                <td className="px-4 py-2 text-[13px]">
                  {trade.hedera_tx_id ? (
                    <div className="relative group/tx">
                      <a
                        href={`https://hashscan.io/testnet/transaction/${trade.hedera_tx_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#c9a84c] hover:text-[#d4b65e] transition-colors inline-flex"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                          <path fillRule="evenodd" d="M4.25 5.5a.75.75 0 00-.75.75v8.5c0 .414.336.75.75.75h8.5a.75.75 0 00.75-.75v-4a.75.75 0 011.5 0v4A2.25 2.25 0 0112.75 17h-8.5A2.25 2.25 0 012 14.75v-8.5A2.25 2.25 0 014.25 4h5a.75.75 0 010 1.5h-5zm7.25-.75a.75.75 0 01.75-.75h3.5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0V6.31l-5.47 5.47a.75.75 0 01-1.06-1.06l5.47-5.47H12.25a.75.75 0 01-.75-.75z" clipRule="evenodd" />
                        </svg>
                      </a>
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 text-[10px] text-white/80 bg-[#1a1a1a] rounded whitespace-nowrap opacity-0 group-hover/tx:opacity-100 transition-opacity pointer-events-none z-50">View on HashScan</span>
                    </div>
                  ) : (
                    <span className="text-white/20">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}
