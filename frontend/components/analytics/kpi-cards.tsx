import type { Analytics } from "@/lib/api";

/** Headline numbers across every chat answer so far. */
export function KpiCards({ totals, latestRun }: { totals: Analytics["totals"]; latestRun: Analytics["eval_runs"][number] | undefined }) {
  const percent = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`);
  const cards = [
    { label: "Answers", value: totals.answers.toLocaleString(), hint: `${totals.conversations} conversations` },
    { label: "Avg latency", value: totals.avg_latency_ms === null ? "–" : `${(totals.avg_latency_ms / 1000).toFixed(1)} s`, hint: "full answer" },
    { label: "Total cost", value: `$${totals.cost_usd.toFixed(4)}`, hint: "priced models only" },
    { label: "Latest hit rate", value: percent(latestRun?.hit_rate), hint: latestRun?.retriever ?? "no eval runs yet" },
    { label: "Latest correctness", value: percent(latestRun?.answer_correctness), hint: "LLM judge" },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map((card) => (
        <div key={card.label} className="rounded-lg border px-3 py-2.5">
          <dt className="truncate text-xs text-muted-foreground">{card.label}</dt>
          <dd className="text-xl font-semibold tabular-nums">{card.value}</dd>
          <dd className="truncate text-[11px] text-muted-foreground">{card.hint}</dd>
        </div>
      ))}
    </dl>
  );
}
