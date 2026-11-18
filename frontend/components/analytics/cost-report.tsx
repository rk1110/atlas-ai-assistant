import { CostChart } from "@/components/analytics/cost-chart";
import type { CostReport as CostReportData } from "@/lib/api";

// Gateway call names (the `name=` of each model call) in plain words.
const PURPOSES: Record<string, string> = {
  chat: "Answer",
  classify_intent: "Routing (question or action?)",
  rewrite_query: "Query rewrite",
  memory_extract: "Memory: save facts",
  summarize_history: "Memory: summarise history",
  describe_image: "Describe image",
  injection_scan: "Injection scan",
  "agent:assistant": "Agent (single)",
  "agent:planner": "Agent: Planner",
  "agent:researcher": "Agent: Researcher",
  "agent:action": "Agent: Action",
  "agent:writer": "Agent: write answer",
  "agent:verifier": "Agent: Verifier",
  eval_answer: "Eval: answer",
  eval_judge: "Eval: judge",
};

const usd = (v: number) => (v > 0 && v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`);

/**
 * Where the money goes (Phase 7B): every model call from the usage ledger, not just final
 * answers. Today's spend against the daily cap, spend per day by model, and the split by
 * purpose and by user.
 */
export function CostReport({ costs }: { costs: CostReportData }) {
  const budget = costs.daily_budget_usd;
  const used = budget ? Math.min(costs.spent_today_usd / budget, 1) : 0;
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-medium">Model spend</h2>
        <p className="text-xs text-muted-foreground">
          Every model call, last 30 days: {usd(costs.total_usd)}.
          {costs.unpriced_calls > 0 && ` ${costs.unpriced_calls} calls to models without a price count as $0.`}
        </p>
      </div>

      <div className="rounded-lg border px-3 py-2.5">
        <div className="flex items-baseline justify-between text-xs">
          <span className="text-muted-foreground">Today (UTC)</span>
          <span className="tabular-nums">
            <span className="text-base font-semibold">{usd(costs.spent_today_usd)}</span>
            {budget !== null && <span className="text-muted-foreground"> of {usd(budget)} daily budget</span>}
          </span>
        </div>
        {budget !== null && (
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted" role="meter" aria-valuenow={Math.round(used * 100)} aria-label="Daily budget used">
            <div className={used >= 0.9 ? "h-full bg-destructive" : "h-full bg-primary"} style={{ width: `${used * 100}%` }} />
          </div>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          Semantic cache: {costs.cache_hits} {costs.cache_hits === 1 ? "answer" : "answers"} reused with no model call, saving{" "}
          {usd(costs.cache_saved_usd)} ({costs.cache_entries} saved answers).
        </p>
      </div>

      {costs.by_day.length === 0 ? (
        <p className="rounded-lg border px-3 py-8 text-center text-sm text-muted-foreground">No model calls recorded yet.</p>
      ) : (
        <>
          <CostChart byDay={costs.by_day} />
          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <table className="w-full text-sm">
              <caption className="pb-1 text-left text-xs text-muted-foreground">By purpose</caption>
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b text-left">
                  <th className="py-1 font-normal">Step</th>
                  <th className="py-1 text-right font-normal">Calls</th>
                  <th className="py-1 text-right font-normal">Cost</th>
                  <th className="py-1 text-right font-normal">Share</th>
                </tr>
              </thead>
              <tbody>
                {costs.by_purpose.map((row) => (
                  <tr key={`${row.purpose}-${row.source}`} className="border-b last:border-0">
                    <td className="py-1">
                      {PURPOSES[row.purpose] ?? row.purpose}
                      {row.source !== "app" && <span className="ml-1 text-xs text-muted-foreground">({row.source})</span>}
                    </td>
                    <td className="py-1 text-right tabular-nums">{row.calls}</td>
                    <td className="py-1 text-right tabular-nums">{usd(row.cost_usd)}</td>
                    <td className="py-1 text-right tabular-nums text-muted-foreground">
                      {costs.total_usd > 0 ? `${Math.round((row.cost_usd / costs.total_usd) * 100)}%` : "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="w-full text-sm">
              <caption className="pb-1 text-left text-xs text-muted-foreground">By user</caption>
              <tbody>
                {costs.by_user.map((row) => (
                  <tr key={row.name} className="border-b last:border-0">
                    <td className="py-1">{row.name}</td>
                    <td className="py-1 text-right tabular-nums text-muted-foreground">{row.calls} calls</td>
                    <td className="py-1 text-right tabular-nums">{usd(row.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
