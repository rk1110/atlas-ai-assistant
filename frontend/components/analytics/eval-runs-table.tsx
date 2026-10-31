import type { EvalRunPoint } from "@/lib/api";

const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)}%`);

/** Every finished eval run, newest first, with what it was testing (its --notes). */
export function EvalRunsTable({ runs }: { runs: EvalRunPoint[] }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium">Eval runs</h2>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-xs">
          <thead className="bg-muted/50 text-left text-muted-foreground">
            <tr>
              {["When", "Retriever", "Model", "Qs", "Hit", "MRR", "Cited", "Correct", "Faithful", "Notes"].map((h) => (
                <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...runs].reverse().map((run) => (
              <tr key={run.id} className="border-t">
                <td className="px-3 py-2 whitespace-nowrap">{new Date(run.started_at).toLocaleDateString()}</td>
                <td className="px-3 py-2">{run.retriever ?? "–"}</td>
                <td className="px-3 py-2 whitespace-nowrap">{run.model_id}</td>
                <td className="px-3 py-2 tabular-nums">{run.question_count}</td>
                <td className="px-3 py-2 tabular-nums">{pct(run.hit_rate)}</td>
                <td className="px-3 py-2 tabular-nums">{run.mrr === null ? "–" : run.mrr.toFixed(2)}</td>
                <td className="px-3 py-2 tabular-nums">{pct(run.cited_correct_rate)}</td>
                <td className="px-3 py-2 tabular-nums">{pct(run.answer_correctness)}</td>
                <td className="px-3 py-2 tabular-nums">{pct(run.faithfulness)}</td>
                <td className="max-w-64 truncate px-3 py-2 text-muted-foreground" title={run.notes ?? ""}>
                  {run.notes ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
