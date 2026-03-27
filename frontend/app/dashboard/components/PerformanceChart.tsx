"use client"

import {
  Area,
  AreaChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

export interface PortfolioSnapshot {
  round: number
  [agentName: string]: number
}

const AGENT_COLORS = [
  "#c9a84c", // gold (first agent)
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
  const allAgentNames = getAgentNames(data)

  const visibleAgents = selectedAgentId
    ? allAgentNames.filter((name) => name === selectedAgentId)
    : allAgentNames

  // Compute tight Y domain from actual data so chart zooms in
  let yMin = Infinity
  let yMax = -Infinity
  for (const snap of data) {
    for (const name of visibleAgents) {
      const val = snap[name]
      if (typeof val === "number" && !isNaN(val)) {
        if (val < yMin) yMin = val
        if (val > yMax) yMax = val
      }
    }
  }
  const yPadding = Math.max((yMax - yMin) * 0.05, 10)
  const yDomain: [number, number] = data.length > 0 && yMin !== Infinity
    ? [Math.floor(yMin - yPadding), Math.ceil(yMax + yPadding)]
    : [9000, 11000]

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-2 border-b border-[#1a1a1a]/50">
        <h3 className="text-xs uppercase tracking-widest text-[#c9a84c]/60" style={{ fontFamily: "var(--font-poppins)" }}>Performance</h3>
      </div>
      <div className="flex-1 min-h-0 px-2 py-1 pb-0">
        {data.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-white/30">Waiting for trading data...</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
              <defs>
                {visibleAgents.map((name) => {
                  const colorIndex = allAgentNames.indexOf(name)
                  const color = AGENT_COLORS[colorIndex % AGENT_COLORS.length]
                  return (
                    <linearGradient
                      key={`gradient-${name}`}
                      id={`gradient-${name.replace(/\s+/g, "-")}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                      <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                    </linearGradient>
                  )
                })}
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
                domain={yDomain}
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
                itemStyle={{ color: "rgba(255,255,255,0.8)" }}
                formatter={(value: number, name: string) => [
                  `$${value.toLocaleString()}`,
                  name,
                ]}
                labelFormatter={(label: number) => `Update ${label}`}
              />
              {visibleAgents.map((name) => {
                const colorIndex = allAgentNames.indexOf(name)
                const color = AGENT_COLORS[colorIndex % AGENT_COLORS.length]
                return (
                  <Area
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={color}
                    strokeWidth={2}
                    fill={`url(#gradient-${name.replace(/\s+/g, "-")})`}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 0, fill: color }}
                  />
                )
              })}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
