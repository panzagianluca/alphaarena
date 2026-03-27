"use client"

import { useState } from "react"
import { createUserWallet } from "@/lib/api"

export function CreateAccountModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (userId: string, name: string, balance: number, hederaAccountId: string) => void
}) {
  const [name, setName] = useState("")
  const [loading, setLoading] = useState(false)

  if (!open) return null

  async function handleCreate() {
    setLoading(true)
    try {
      const displayName = name.trim() || "Anonymous"
      const wallet = await createUserWallet(displayName)
      localStorage.setItem("alphaarena_user_id", wallet.user_id)
      localStorage.setItem("alphaarena_user_name", displayName)
      localStorage.setItem("alphaarena_hedera_account_id", wallet.hedera_account_id)
      onCreated(wallet.user_id, displayName, wallet.arena_balance, wallet.hedera_account_id)
      onClose()
      setName("")
    } catch (err) {
      console.error("Failed to create account:", err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

      <div className="relative bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl w-full max-w-sm mx-4 p-6">
        <h2
          className="text-lg font-light text-white/90 mb-1"
          style={{ fontFamily: "var(--font-poppins)" }}
        >
          Join AlphaArena
        </h2>
        <p className="text-[12px] text-white/30 mb-6">
          Get a demo wallet with 50,000 aUSD to deploy agents and allocate capital.
        </p>

        <div className="mb-6">
          <span className="text-[10px] text-white/30 uppercase tracking-widest">
            Your Name
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Enter your name..."
            className="w-full mt-2 bg-black border border-[#1a1a1a] rounded-lg p-3 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:border-[#c9a84c]/30 transition-colors"
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            autoFocus
          />
        </div>

        <button
          onClick={handleCreate}
          disabled={loading}
          className="w-full bg-[#c9a84c] text-black text-sm font-medium py-3 rounded-full hover:bg-[#d4b55a] transition-all disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
        >
          {loading ? "Creating wallet..." : "Create Account"}
        </button>

        {loading && (
          <p className="text-[11px] text-white/30 text-center mt-3">
            Assigning Hedera wallet and funding 50,000 aUSD...
          </p>
        )}
      </div>
    </div>
  )
}
