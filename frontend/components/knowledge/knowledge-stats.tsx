import type { KnowledgeDocument } from "@/lib/api";

/** Headline numbers: how much Atlas knows, and whether anything needs attention. */
export function KnowledgeStats({ documents, embeddingModel }: { documents: KnowledgeDocument[]; embeddingModel: string }) {
  const chunks = documents.reduce((sum, d) => sum + d.chunk_count, 0);
  const sources = new Set(documents.map((d) => d.source)).size;
  const failed = documents.filter((d) => d.status === "failed").length;
  const stats = [
    { label: "Documents", value: documents.length },
    { label: "Chunks (searchable passages)", value: chunks },
    { label: "Sources", value: sources },
    { label: "Failed", value: failed, alert: failed > 0 },
  ];
  return (
    <div className="flex flex-col gap-2">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg border px-3 py-2.5">
            <dt className="truncate text-xs text-muted-foreground">{s.label}</dt>
            <dd className={`text-xl font-semibold tabular-nums ${s.alert ? "text-destructive" : ""}`}>
              {s.value.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-muted-foreground">
        Embedded with <code>{embeddingModel}</code>. Searched by meaning (pgvector), by keyword (BM25) and through the knowledge graph (Neo4j).
      </p>
    </div>
  );
}
