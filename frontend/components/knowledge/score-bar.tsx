/**
 * A relevance score as a small bar plus the number. What it measures depends on the strategy:
 * cosine similarity (vector, 0-1), raw BM25 (keyword, unbounded: the bar caps at 1), RRF
 * scaled to "first everywhere" (hybrid, 0-1) or the cross-encoder's probability (rerank, 0-1).
 * Compare ranks across strategies, not raw scores.
 */
export function ScoreBar({ score }: { score: number }) {
  return (
    <span className="flex shrink-0 items-center gap-1.5 tabular-nums text-muted-foreground" title="Relevance score">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-muted">
        <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }} />
      </span>
      {score.toFixed(2)}
    </span>
  );
}
