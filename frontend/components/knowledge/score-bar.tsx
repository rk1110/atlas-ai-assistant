/** A relevance score (cosine similarity, 0 to 1) as a small bar plus the number. */
export function ScoreBar({ score }: { score: number }) {
  return (
    <span className="flex shrink-0 items-center gap-1.5 tabular-nums text-muted-foreground" title="Cosine similarity">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-muted">
        <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }} />
      </span>
      {score.toFixed(2)}
    </span>
  );
}
