"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { EvalRunPoint } from "@/lib/api";

export interface Series {
  key: keyof EvalRunPoint;
  label: string;
  color: string;
}

/**
 * Eval scores across runs, oldest left. Each point is one `python -m evals.run`: a change
 * (prompt, retriever, model) shows up as a step. Runs without a metric leave a gap.
 */
export function QualityChart({ title, hint, runs, series }: { title: string; hint: string; runs: EvalRunPoint[]; series: Series[] }) {
  const data = runs.map((run, i) => ({
    ...run,
    label: `#${i + 1} ${run.retriever ?? "none"}`,
  }));
  return (
    <section className="flex flex-col gap-2">
      <div>
        <h2 className="text-sm font-medium">{title}</h2>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <div className="h-64 w-full rounded-lg border p-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} interval="preserveStartEnd" />
            <YAxis domain={[0, 1]} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
            <Tooltip
              formatter={(value) => (typeof value === "number" ? `${(value * 100).toFixed(1)}%` : value)}
              labelFormatter={(_, payload) => {
                const run = payload?.[0]?.payload as (EvalRunPoint & { label: string }) | undefined;
                return run ? `${run.label} · ${run.model_id} · ${new Date(run.started_at).toLocaleString()}` : "";
              }}
              contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {series.map((s) => (
              <Line key={String(s.key)} type="monotone" dataKey={String(s.key)} name={s.label} stroke={s.color} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
