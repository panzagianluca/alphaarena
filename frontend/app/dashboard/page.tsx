"use client"

import { useState, useEffect, useCallback } from "react"
import { fetchAgents, fetchLeague, fetchFeed, fetchUserBalance, fetchPortfolioHistory, startSeason, type Agent, type Trade, type Season } from "@/lib/api"
import { useWebSocket } from "@/hooks/useWebSocket"
import { DashboardHeader } from "./components/DashboardHeader"
import { Leaderboard } from "./components/Leaderboard"
import { TradeFeed } from "./components/TradeFeed"
import { CreateAgentModal } from "./components/CreateAgentModal"
import { CreateAccountModal } from "./components/CreateAccountModal"
import { PerformanceChart, type PortfolioSnapshot } from "./components/PerformanceChart"
import { PortfolioModal } from "./components/PortfolioModal"

export default function Dashboard() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [trades, setTrades] = useState<Trade[]>([])
  const [season, setSeason] = useState<Season | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [userId, setUserId] = useState<string | null>(null)
  const [userName, setUserName] = useState<string | null>(null)
  const [userBalance, setUserBalance] = useState<number | null>(null)
  const [portfolioHistory, setPortfolioHistory] = useState<PortfolioSnapshot[]>([])
  const [accountModalOpen, setAccountModalOpen] = useState(false)
  const [portfolioModalOpen, setPortfolioModalOpen] = useState(false)
  const [hederaAccountId, setHederaAccountId] = useState<string | null>(null)

  const isLoggedIn = userId !== null

  // Initial data load
  const loadData = useCallback(async () => {
    try {
      const [agentsData, leagueData, feedData, historyData] = await Promise.all([
        fetchAgents(),
        fetchLeague(),
        fetchFeed(),
        fetchPortfolioHistory(),
      ])
      setAgents(agentsData)
      setSeason(leagueData.season)
      setTrades(feedData)
      if (historyData.length > 0) {
        setPortfolioHistory(historyData as PortfolioSnapshot[])
      }
    } catch (err) {
      console.error("Failed to load data:", err)
    } finally {
      setLoading(false)
    }
  }, [])

  // Restore session from localStorage — auto-logout if user no longer exists
  useEffect(() => {
    const id = localStorage.getItem("alphaarena_user_id")
    const name = localStorage.getItem("alphaarena_user_name")
    if (id) {
      fetchUserBalance(id).then((data: Record<string, unknown>) => {
        if (!data.hedera_account_id) {
          // User doesn't exist in DB anymore — clear stale session
          localStorage.removeItem("alphaarena_user_id")
          localStorage.removeItem("alphaarena_user_name")
          localStorage.removeItem("alphaarena_hedera_account_id")
        } else {
          setUserId(id)
          setUserName(name || "Anonymous")
          setHederaAccountId(localStorage.getItem("alphaarena_hedera_account_id"))
          setUserBalance((data.arena_balance as number) ?? 0)
        }
      })
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  function handleAccountCreated(newUserId: string, name: string, balance: number, hederaAccId: string) {
    setUserId(newUserId)
    setUserName(name)
    setUserBalance(balance)
    setHederaAccountId(hederaAccId)
  }

  function handleLogout() {
    localStorage.removeItem("alphaarena_user_id")
    localStorage.removeItem("alphaarena_user_name")
    localStorage.removeItem("alphaarena_hedera_account_id")
    setUserId(null)
    setUserName(null)
    setUserBalance(null)
    setHederaAccountId(null)
  }

  async function handleStartSeason() {
    await startSeason(1440, 60)
    loadData()
  }

  // Resolve selectedAgentId to agent name for the chart
  const selectedAgentName = selectedAgentId
    ? agents.find((a) => a.id === selectedAgentId)?.name ?? null
    : null

  // WebSocket live updates
  const { connected } = useWebSocket(
    useCallback((msg: { type: string; data: unknown }) => {
      switch (msg.type) {
        case "trades": {
          const newTrades = msg.data as Trade[]
          setTrades((prev) => [...newTrades, ...prev].slice(0, 100))
          break
        }
        case "leaderboard": {
          const lb = msg.data as Array<{ agent_id: string; rank: number; pnl_pct: number; composite_score: number; total_trades: number }>
          setAgents((prev) =>
            prev.map((a) => {
              const update = lb.find((u) => u.agent_id === a.id)
              return update
                ? { ...a, rank: update.rank, pnl_pct: update.pnl_pct, total_trades: update.total_trades }
                : a
            })
          )
          break
        }
        case "new_agent": {
          const newAgent = msg.data as Agent
          setAgents((prev) => [...prev, newAgent])
          break
        }
        case "season_end": {
          loadData()
          break
        }
        case "round_complete": {
          const roundData = msg.data as {
            round: number
            portfolios: Record<string, { name: string; value: number }>
          }
          const snapshot: PortfolioSnapshot = { round: roundData.round }
          for (const [, info] of Object.entries(roundData.portfolios)) {
            snapshot[info.name] = info.value
          }
          setPortfolioHistory((prev) => [...prev, snapshot])
          break
        }
      }
    }, [loadData])
  )

  if (loading) {
    return (
      <div className="h-screen bg-black flex flex-col">
        {/* Header skeleton */}
        <div className="h-14 border-b border-[#1a1a1a] px-4 flex items-center gap-4">
          <div className="h-5 w-32 animate-pulse bg-[#111] rounded" />
          <div className="ml-auto flex gap-3">
            <div className="h-8 w-24 animate-pulse bg-[#111] rounded" />
            <div className="h-8 w-24 animate-pulse bg-[#111] rounded" />
          </div>
        </div>

        {/* Main: leaderboard + chart */}
        <div className="flex-1 flex min-h-0 p-4 gap-4">
          {/* Leaderboard skeleton — 4 cards */}
          <div className="w-[380px] shrink-0 flex flex-col gap-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-20 animate-pulse bg-[#111] rounded-lg" />
            ))}
          </div>
          {/* Chart skeleton */}
          <div className="flex-1">
            <div className="h-full animate-pulse bg-[#111] rounded-lg" />
          </div>
        </div>

        {/* Trade table skeleton — horizontal rows */}
        <div className="h-[280px] shrink-0 border-t border-[#1a1a1a] p-4 flex flex-col gap-2">
          <div className="h-4 w-48 animate-pulse bg-[#111] rounded" />
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-8 animate-pulse bg-[#111] rounded" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen bg-black text-white flex flex-col">
      <DashboardHeader
        season={season}
        connected={connected}
        onCreateClick={() => setModalOpen(true)}
        onCreateAccount={() => setAccountModalOpen(true)}
        onStartSeason={handleStartSeason}
        onLogout={handleLogout}
        onOpenPortfolio={() => setPortfolioModalOpen(true)}
        userBalance={userBalance}
        userName={userName}
        isLoggedIn={isLoggedIn}
        hederaAccountId={hederaAccountId}
      />

      {/* Main: leaderboard + chart */}
      <div className="flex-1 flex min-h-0">
        <div className="w-[440px] shrink-0 flex flex-col min-h-0 border-r border-[#1a1a1a]/50">
          <Leaderboard
            agents={agents}
            selectedAgentId={selectedAgentId}
            onSelectAgent={setSelectedAgentId}
            onBalanceUpdate={(b) => setUserBalance(b)}
          />
        </div>
        <div className="flex-1 flex flex-col min-h-0">
          <PerformanceChart data={portfolioHistory} selectedAgentId={selectedAgentName} />
        </div>
      </div>

      {/* Bottom: trade table */}
      <div className="h-[280px] shrink-0">
        <TradeFeed trades={trades} />
      </div>

      {/* Modals */}
      <CreateAgentModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={() => {
          loadData()
          if (userId) fetchUserBalance(userId).then((d) => setUserBalance(d.arena_balance))
        }}
      />
      <CreateAccountModal
        open={accountModalOpen}
        onClose={() => setAccountModalOpen(false)}
        onCreated={handleAccountCreated}
      />
      {userId && (
        <PortfolioModal
          isOpen={portfolioModalOpen}
          onClose={() => setPortfolioModalOpen(false)}
          userId={userId}
          onBalanceUpdate={(newBal) => setUserBalance(newBal)}
        />
      )}
    </div>
  )
}
