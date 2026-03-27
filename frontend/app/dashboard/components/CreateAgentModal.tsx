"use client"

import { useState, useEffect } from "react"
import { createAgent, fetchTemplates, type AgentTemplate } from "@/lib/api"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { toast } from "sonner"

const INSTRUMENTS = ["BTC", "ETH", "HBAR", "DOGE"] as const

const MODEL_OPTIONS = [
  { value: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash (Fast)" },
  { value: "anthropic/claude-3.5-haiku", label: "Claude Haiku (Fast)" },
  { value: "anthropic/claude-3.5-sonnet", label: "Claude Sonnet (Smart)" },
  { value: "google/gemini-2.5-pro", label: "Gemini 2.5 Pro (Smart)" },
  { value: "x-ai/grok-3-mini-beta", label: "Grok 3 Mini (xAI)" },
  { value: "meta-llama/llama-3.3-70b-instruct", label: "Llama 3.3 70B (Groq)" },
]

export function CreateAgentModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: () => void
}) {
  const [agentName, setAgentName] = useState("")
  const [thesis, setThesis] = useState("")
  const [instruments, setInstruments] = useState<string[]>([...INSTRUMENTS])
  const [model, setModel] = useState<string>(MODEL_OPTIONS[0].value)
  const [loading, setLoading] = useState(false)
  const [templates, setTemplates] = useState<Record<string, AgentTemplate>>({})

  useEffect(() => {
    fetchTemplates().then(setTemplates).catch(() => {})
  }, [])

  if (!open) return null

  function toggleInstrument(inst: string) {
    setInstruments((prev) =>
      prev.includes(inst) ? prev.filter((i) => i !== inst) : [...prev, inst]
    )
  }

  async function handleSubmit() {
    if (!thesis.trim()) return
    setLoading(true)
    try {
      const userId = localStorage.getItem("alphaarena_user_id") || undefined
      await createAgent(
        thesis,
        agentName.trim() || undefined,
        userId,
        instruments,
        model,
      )
      toast.success("Agent deployed! It will start trading shortly.")
      setThesis("")
      setAgentName("")
      setInstruments([...INSTRUMENTS])
      setModel(MODEL_OPTIONS[0].value)
      onCreated()
      onClose()
    } catch (err) {
      console.error("Failed to create agent:", err)
      toast.error("Failed to deploy agent. Check your aUSD balance.")
    } finally {
      setLoading(false)
    }
  }

  function useTemplate(t: AgentTemplate) {
    setThesis(t.thesis)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl w-full max-w-lg mx-4 p-6">
        <div className="flex items-center justify-between mb-6">
          <h2
            className="text-lg font-light text-white/90"
            style={{ fontFamily: "var(--font-poppins)" }}
          >
            Deploy Your Agent
          </h2>
          <button
            onClick={onClose}
            className="text-white/30 hover:text-white/60 transition-colors text-lg cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Agent Name */}
        <div className="mb-4">
          <span className="text-[10px] text-white/30 uppercase tracking-widest">
            Agent Name
          </span>
          <input
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            placeholder="Leave blank for AI-generated name"
            className="w-full mt-2 bg-black border border-[#1a1a1a] rounded-lg p-3 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:border-[#c9a84c]/30 transition-colors"
          />
        </div>

        {/* Templates */}
        <div className="mb-2">
          <span className="text-[10px] text-white/30 uppercase tracking-widest">
            Templates
          </span>
          <div className="flex flex-wrap gap-2 mt-2">
            {Object.entries(templates).map(([key, t]) => (
              <button
                key={key}
                onClick={() => useTemplate(t)}
                className="text-[11px] text-white/50 border border-[#1a1a1a] rounded-full px-3 py-1 hover:border-[#c9a84c]/30 hover:text-[#c9a84c] transition-all cursor-pointer"
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Trading Thesis */}
        <div className="mb-4">
          <span className="text-[10px] text-white/30 uppercase tracking-widest">
            Trading Thesis <span className="text-red-400/60">*</span>
          </span>
          <textarea
            value={thesis}
            onChange={(e) => setThesis(e.target.value)}
            placeholder="I believe ETH will outperform this cycle. Buy every dip below 5%. Hold strong. Never more than 40% in one position..."
            className="w-full mt-2 bg-black border border-[#1a1a1a] rounded-lg p-3 text-sm text-white/80 placeholder:text-white/20 resize-none h-32 focus:outline-none focus:border-[#c9a84c]/30 transition-colors"
          />
        </div>

        {/* Instruments */}
        <div className="mb-4">
          <span className="text-[10px] text-white/30 uppercase tracking-widest">
            Instruments
          </span>
          <div className="flex flex-wrap gap-3 mt-2">
            {INSTRUMENTS.map((inst) => (
              <label
                key={inst}
                className="flex items-center gap-2 cursor-pointer select-none"
              >
                <input
                  type="checkbox"
                  checked={instruments.includes(inst)}
                  onChange={() => toggleInstrument(inst)}
                  className="sr-only peer"
                />
                <span className="w-4 h-4 rounded border border-[#1a1a1a] bg-black flex items-center justify-center peer-checked:border-[#c9a84c] peer-checked:bg-[#c9a84c]/20 transition-all">
                  {instruments.includes(inst) && (
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                      <path d="M2 5L4 7L8 3" stroke="#c9a84c" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className="text-xs text-white/60">{inst}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Model */}
        <div className="mb-6">
          <span className="text-[10px] text-white/30 uppercase tracking-widest">
            Model
          </span>
          <div className="mt-2">
            <Select value={model} onValueChange={(v) => { if (v) setModel(v) }}>
              <SelectTrigger className="w-full bg-black border-[#1a1a1a] text-sm text-white/80 hover:border-[#2a2a2a] focus:ring-[#c9a84c]/20 focus:ring-offset-0">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#0a0a0a] border-[#1a1a1a]">
                {MODEL_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value} className="text-white/80 focus:bg-[#1a1a1a] focus:text-white cursor-pointer">
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Cost display */}
        <p className="text-center text-sm mb-4" style={{ color: "#c9a84c" }}>
          Deployment cost: 1,000 aUSD
        </p>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!thesis.trim() || instruments.length === 0 || loading}
          className="w-full bg-[#c9a84c] text-black text-sm font-medium py-3 rounded-full hover:bg-[#d4b55a] transition-all disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
        >
          {loading ? "Deploying..." : "Deploy Agent \u2014 1,000 aUSD"}
        </button>

        {loading && (
          <p className="text-[11px] text-white/30 text-center mt-3">
            Generating persona with AI... this takes ~5 seconds
          </p>
        )}
      </div>
    </div>
  )
}
