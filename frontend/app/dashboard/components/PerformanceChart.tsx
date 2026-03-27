"use client"

import { useEffect, useRef } from "react"
import { createChart, ColorType, IChartApi, ISeriesApi, Time, AreaSeries } from "lightweight-charts"

export interface PortfolioSnapshot {
  round: number
  [agentName: string]: number
}

const AGENT_COLORS = [
  "#c9a84c", // gold
  "#4ade80", // green
  "#f87171", // red
  "#60a5fa", // blue
  "#a78bfa", // purple
  "#f97316", // orange
  "#22d3ee", // cyan
  "#ec4899", // pink
  "#eab308", // yellow
  "#14b8a6", // teal
]

function getAgentNames(data: PortfolioSnapshot[]): string[] {
  const names = new Set<string>()
  for (const snap of data) {
    for (const key of Object.keys(snap)) {
      if (key !== "round") names.add(key)
    }
  }
  return Array.from(names)
}

export function PerformanceChart({
  data,
  selectedAgentId,
}: {
  data: PortfolioSnapshot[]
  selectedAgentId: string | null
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesMapRef = useRef<Map<string, ISeriesApi<"Area", Time>>>(new Map())
  const prevDataLenRef = useRef(0)
  const prevSelectedRef = useRef(selectedAgentId)

  // Create chart once on mount
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255,255,255,0.3)",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1a1a1a" },
        horzLines: { color: "#1a1a1a" },
      },
      crosshair: {
        vertLine: { color: "rgba(201,168,76,0.3)", width: 1, style: 2 },
        horzLine: { color: "rgba(201,168,76,0.3)", width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: "#1a1a1a",
      },
      timeScale: {
        borderColor: "#1a1a1a",
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    })

    chartRef.current = chart

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 0 && height > 0) chart.applyOptions({ width, height })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesMapRef.current.clear()
      prevDataLenRef.current = 0
    }
  }, [])

  // Update series data — incremental updates, no full re-render
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || data.length === 0) return

    const allNames = getAgentNames(data)
    const visibleNames = selectedAgentId
      ? allNames.filter((n) => n === selectedAgentId)
      : allNames

    // Selection changed → force full redraw
    const selectionChanged = prevSelectedRef.current !== selectedAgentId
    if (selectionChanged) {
      prevDataLenRef.current = 0
      prevSelectedRef.current = selectedAgentId
    }

    // Toggle visibility
    for (const [name, series] of seriesMapRef.current) {
      series.applyOptions({ visible: visibleNames.includes(name) })
    }

    const isIncremental = !selectionChanged && data.length > prevDataLenRef.current

    for (const name of visibleNames) {
      const ci = allNames.indexOf(name)
      const color = AGENT_COLORS[ci % AGENT_COLORS.length]

      let series = seriesMapRef.current.get(name)
      if (!series) {
        series = chart.addSeries(AreaSeries, {
          lineColor: color,
          topColor: color + "4D",
          bottomColor: color + "05",
          lineWidth: 2,
          crosshairMarkerVisible: true,
          crosshairMarkerRadius: 4,
          crosshairMarkerBackgroundColor: color,
          priceFormat: {
            type: "custom",
            formatter: (price: number) =>
              price >= 1000 ? `$${(price / 1000).toFixed(1)}k` : `$${price.toFixed(0)}`,
          },
          title: name,
        })
        seriesMapRef.current.set(name, series)
      }

      series.applyOptions({ visible: true })

      if (isIncremental) {
        // Only push new data points — no re-render
        const newSlice = data.slice(prevDataLenRef.current)
        for (const snap of newSlice) {
          const v = snap[name]
          if (typeof v === "number" && !isNaN(v)) {
            series.update({ time: snap.round as Time, value: v })
          }
        }
      } else {
        // Full set (first load or selection change)
        const pts = data
          .filter((s) => typeof s[name] === "number" && !isNaN(s[name]))
          .map((s) => ({ time: s.round as Time, value: s[name] as number }))
        series.setData(pts)
      }
    }

    prevDataLenRef.current = data.length
    chart.timeScale().fitContent()
  }, [data, selectedAgentId])

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-2 border-b border-[#1a1a1a]/50">
        <h3
          className="text-xs uppercase tracking-widest text-[#c9a84c]/60"
          style={{ fontFamily: "var(--font-poppins)" }}
        >
          Performance
        </h3>
      </div>
      <div className="flex-1 min-h-0 relative">
        {data.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <p className="text-xs text-white/30">Waiting for trading data...</p>
          </div>
        )}
        <div ref={containerRef} className="w-full h-full" />
      </div>
    </div>
  )
}
