import { CostReport } from "@/components/analytics/cost-report";
import { EvalRunsTable } from "@/components/analytics/eval-runs-table";
import { KpiCards } from "@/components/analytics/kpi-cards";
import { QualityChart } from "@/components/analytics/quality-chart";
import { UsageChart } from "@/components/analytics/usage-chart";
import type { Analytics } from "@/lib/api";

/**
 * Analytics v1: is Atlas getting better (eval scores per run), and how is it used (answers,
 * latency, cost)? All from Postgres: eval_runs, messages and llm_usage (every model call, Phase 7B).
 * Langfuse has the per-trace detail.
 */
export function AnalyticsView({ data }: { data: Analytics }) {
  const runs = data.eval_runs;
  const judged = runs.filter((r) => r.answer_correctness !== null);
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-6">
      <KpiCards totals={data.totals} latestRun={runs.at(-1)} />
      <div className="grid gap-8 lg:grid-cols-2">
        <QualityChart
          title="Retrieval quality"
          hint="Did search find the right document (hit rate), how high (MRR), and did the answer cite it?"
          runs={runs.filter((r) => r.hit_rate !== null)}
          series={[
            { key: "hit_rate", label: "Hit rate", color: "var(--chart-1)" },
            { key: "mrr", label: "MRR", color: "var(--chart-3)" },
            { key: "cited_correct_rate", label: "Cited correct", color: "var(--chart-2)" },
          ]}
        />
        <QualityChart
          title="Answer quality (LLM judge)"
          hint="Graded by the cheap model: right facts, supported by the sources, relevant sources first."
          runs={judged}
          series={[
            { key: "answer_correctness", label: "Correctness", color: "var(--chart-4)" },
            { key: "faithfulness", label: "Faithfulness", color: "var(--chart-1)" },
            { key: "context_precision", label: "Context precision", color: "var(--chart-5)" },
          ]}
        />
      </div>
      <CostReport costs={data.costs} />
      <UsageChart usage={data.usage} />
      <EvalRunsTable runs={runs} />
    </div>
  );
}
