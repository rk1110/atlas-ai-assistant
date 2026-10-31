/**
 * Human-readable names for the retrieval strategies (backend/retrieval/__init__.py).
 * Unknown names fall back to the raw id, so a new backend strategy still shows up.
 */
const STRATEGIES: Record<string, { label: string; hint: string }> = {
  vector: { label: "Vector", hint: "Same meaning: embedding similarity (pgvector)" },
  keyword: { label: "Keyword", hint: "Same words: BM25 over Postgres full-text search" },
  hybrid: { label: "Hybrid", hint: "Vector + keyword, fused with Reciprocal Rank Fusion" },
  hybrid_rerank: { label: "Hybrid + rerank", hint: "Hybrid, then a cross-encoder re-orders the top 10" },
  hybrid_graph: { label: "Hybrid + graph", hint: "Vector + keyword + knowledge-graph facts, fused" },
  graph: { label: "Graph only", hint: "Facts from the knowledge graph (Neo4j)" },
};

/** The strategies the "Compare" view runs side by side. */
export const COMPARED_STRATEGIES = ["vector", "keyword", "hybrid", "hybrid_rerank", "hybrid_graph"];

export function strategyLabel(id: string): string {
  return STRATEGIES[id]?.label ?? id;
}

export function strategyHint(id: string): string {
  return STRATEGIES[id]?.hint ?? "";
}
