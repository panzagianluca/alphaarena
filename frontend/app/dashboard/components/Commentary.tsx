"use client"

export function Commentary({ text }: { text: string }) {
  if (!text) return null

  return (
    <div className="border-t border-[#1a1a1a] px-5 py-3">
      <div className="flex items-start gap-3">
        <span className="text-[10px] text-[#c9a84c] uppercase tracking-widest shrink-0 mt-0.5">
          Commentary
        </span>
        <p className="text-[12px] text-white/40 leading-relaxed">{text}</p>
      </div>
    </div>
  )
}
