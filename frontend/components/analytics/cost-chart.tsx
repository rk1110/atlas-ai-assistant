"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { CostReport } from "@/lib/api";

const COLORS = ["var(--chart-1)", "var(--chart-3)", "var(--chart-2)", "var(--chart-4)", "var(--chart-5)"];

/** Spend per day, one stacked bar segment per model: which model the money goes to. */
export function CostChart({ byDay }: { byDay: CostReport["by_day"] }) {
  const models = [...new Set(byDay.map((row) => row.model_id))];
  // One chart row per day: { day, "claude-sonnet": 0.12, "claude-haiku": 0.01 }
  const days = new Map<string, Record<string, number | string>>();
  for (const row of byDay) {
    const day = days.get(row.day) ?? { day: row.day };
    day[row.model_id] = row.cost_usd;
    days.set(row.day, day);
  }
  return (
    <div className="h-56 w-full rounded-lg border p-2">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={[...days.values()]} margin={{ top: 8, right: 0, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey="day" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
          <YAxis tickFormatter={(v: number) => `$${v.toFixed(2)}`} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
          <Tooltip
            formatter={(v) => `$${Number(v).toFixed(4)}`}
            contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {models.map((model, i) => (
            <Bar key={model} dataKey={model} stackId="cost" fill={COLORS[i % COLORS.length]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
