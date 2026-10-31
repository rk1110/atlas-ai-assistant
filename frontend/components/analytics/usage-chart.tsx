"use client";

import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { UsageDay } from "@/lib/api";

/** Chat answers per day (bars) and their average latency (line), last 30 days. */
export function UsageChart({ usage }: { usage: UsageDay[] }) {
  return (
    <section className="flex flex-col gap-2">
      <div>
        <h2 className="text-sm font-medium">Chat usage</h2>
        <p className="text-xs text-muted-foreground">Answers per day and their average latency, last 30 days.</p>
      </div>
      {usage.length === 0 ? (
        <p className="rounded-lg border px-3 py-8 text-center text-sm text-muted-foreground">No answers in the last 30 days.</p>
      ) : (
        <div className="h-64 w-full rounded-lg border p-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={usage} margin={{ top: 8, right: 0, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <YAxis yAxisId="answers" allowDecimals={false} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <YAxis yAxisId="latency" orientation="right" tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}s`} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="answers" dataKey="answers" name="Answers" fill="var(--chart-1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar yAxisId="answers" dataKey="errors" name="Errors" fill="var(--chart-5)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Line yAxisId="latency" dataKey="avg_latency_ms" name="Avg latency (ms)" stroke="var(--chart-3)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
