import type { RetrievedChunk } from "@/lib/api";

/**
 * Why a chunk is where it is: which retrievers found it and at what rank (hybrid), where it
 * was before the cross-encoder moved it (rerank), or that it came from the knowledge graph.
 */
export function RankBadges({ chunk }: { chunk: RetrievedChunk }) {
  const { ranks, rank_before_rerank: before, graph_entities: entities } = chunk.metadata;
  const badges: string[] = [];
  if (ranks) badges.push(...Object.entries(ranks).map(([name, rank]) => `${name} #${rank}`));
  if (before !== undefined) badges.push(`before rerank #${before}`);
  if (entities?.length) badges.push(`graph: ${entities.join(", ")}`);
  if (badges.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {badges.map((badge) => (
        <span key={badge} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground tabular-nums">
          {badge}
        </span>
      ))}
    </span>
  );
}
