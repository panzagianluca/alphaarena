"use client"

import Link from "next/link"
import type { Season } from "@/lib/api"
import { useState, useEffect, useRef } from "react"

function useClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

export function DashboardHeader({
  season,
  connected,
  onCreateClick,
  onCreateAccount,
  onStartSeason,
  onLogout,
  onOpenPortfolio,
  userBalance,
  userName,
  isLoggedIn,
  hederaAccountId,
}: {
  season: Season | null
  connected: boolean
  onCreateClick: () => void
  onCreateAccount: () => void
  onStartSeason: () => void
  onLogout: () => void
  onOpenPortfolio: () => void
  userBalance: number | null
  userName: string | null
  isLoggedIn: boolean
  hederaAccountId: string | null
}) {
  const now = useClock()
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  const [profileOpen, setProfileOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setProfileOpen(false)
      }
    }
    if (profileOpen) {
      document.addEventListener("mousedown", handleClickOutside)
      return () => document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [profileOpen])

  function truncateAccountId(id: string | null): string {
    if (!id) return ""
    if (id.length <= 12) return id
    return `${id.slice(0, 8)}...${id.slice(-3)}`
  }

  return (
    <div className="border-b border-[#1a1a1a] h-14 px-5 flex items-center justify-between shrink-0">
      {/* Left side */}
      <div className="flex items-center gap-4">
        <Link href="/" className="flex items-center gap-2">
          <img src="/alphaarena.svg" alt="AlphaArena" className="w-6 h-6" />
          <span
            className="text-[17px] font-light tracking-tight"
            style={{ fontFamily: "var(--font-poppins)" }}
          >
            Alpha<span className="text-[#c9a84c]">Arena</span>
          </span>
        </Link>

        <div className="w-px h-5 bg-[#1a1a1a]" />

        {season ? (
          <div className="flex items-center gap-3">
            <span className="text-xs text-white/40 uppercase tracking-widest">
              Season {season.id}
            </span>
            <span className="text-xs text-white/60 font-mono">
              {(() => {
                const started = new Date(season.started_at)
                const elapsed = Math.max(0, Math.floor((now.getTime() - started.getTime()) / 1000))
                const h = Math.floor(elapsed / 3600)
                const m = Math.floor((elapsed % 3600) / 60)
                const s = elapsed % 60
                if (h > 0) return `${h}h ${m}m elapsed`
                if (m > 0) return `${m}m ${s}s elapsed`
                return `${s}s elapsed`
              })()}
            </span>
            <span className="text-[10px] text-white/20 font-mono">
              U{season.rounds_completed}
            </span>
          </div>
        ) : (
          <button
            onClick={onStartSeason}
            className="text-xs text-[#c9a84c] border border-[#c9a84c]/30 px-3 py-1 rounded-full hover:bg-[#c9a84c]/10 transition-all cursor-pointer uppercase tracking-widest"
          >
            Start Season
          </button>
        )}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        <span className="text-xs text-white/30 font-mono">{timeStr}</span>

        <div className="flex items-center gap-1.5">
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${connected ? "bg-green-400 animate-pulse" : "bg-red-400"}`}
          />
          <span className="text-[10px] text-white/40 uppercase tracking-widest">
            {connected ? "Live" : "Offline"}
          </span>
        </div>

        <a
          href="https://hashscan.io/testnet/account/0.0.8386917"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] text-[#c9a84c]/40 hover:text-[#c9a84c] transition-colors"
        >
          ⛓ Verify
        </a>

        {isLoggedIn ? (
          <>
            {/* Create Agent -- solid button */}
            <button
              onClick={onCreateClick}
              className="bg-[#c9a84c] text-black text-[12px] font-medium px-4 py-1.5 rounded-full hover:bg-[#d4b55a] transition-all cursor-pointer"
            >
              + Create Agent
            </button>

            {/* Profile circle + dropdown */}
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setProfileOpen(!profileOpen)}
                className="w-8 h-8 rounded-full bg-[#c9a84c]/20 border border-[#c9a84c]/30 flex items-center justify-center text-[12px] text-[#c9a84c] font-medium cursor-pointer hover:bg-[#c9a84c]/30 transition-all"
              >
                {(userName || "U")[0].toUpperCase()}
              </button>

              {profileOpen && (
                <div className="absolute right-0 top-10 w-56 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg shadow-xl z-50 py-2">
                  <div className="px-3 py-2">
                    <p className="text-sm text-white font-semibold">
                      {userName || "Anonymous"}
                    </p>
                    {hederaAccountId && (
                      <p className="text-[10px] text-white/40 font-mono mt-0.5">
                        {truncateAccountId(hederaAccountId)}
                      </p>
                    )}
                    <p className="text-sm font-mono mt-1.5" style={{ color: "#c9a84c" }}>
                      {(userBalance ?? 0).toLocaleString()} aUSD
                    </p>
                  </div>
                  <div className="border-t border-[#1a1a1a] my-1" />
                  <button
                    onClick={() => {
                      setProfileOpen(false)
                      onOpenPortfolio()
                    }}
                    className="w-full text-left px-3 py-2 text-xs text-white/60 hover:bg-white/[0.03] transition-colors cursor-pointer"
                  >
                    My Portfolio
                  </button>
                  <button
                    onClick={() => {
                      setProfileOpen(false)
                      onLogout()
                    }}
                    className="w-full text-left px-3 py-2 text-xs text-red-400 hover:bg-white/[0.03] transition-colors cursor-pointer"
                  >
                    Logout
                  </button>
                </div>
              )}
            </div>
          </>
        ) : (
          /* Not logged in -- Create Account button */
          <button
            onClick={onCreateAccount}
            className="bg-[#c9a84c] text-black text-[12px] font-medium px-4 py-1.5 rounded-full hover:bg-[#d4b55a] transition-all cursor-pointer"
          >
            Create Account
          </button>
        )}
      </div>
    </div>
  )
}
