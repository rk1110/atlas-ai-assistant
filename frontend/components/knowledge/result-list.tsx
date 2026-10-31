import { RankBadges } from "@/components/knowledge/rank-badges";
import { ScoreBar } from "@/components/knowledge/score-bar";
import type { RetrievedChunk } from "@/lib/api";

/** One strategy's ranked results. `compact` is the narrow column of the Compare view. */
export function ResultList({
  chunks,
  compact = false,
  onOpenDocument,
}: {
  chunks: RetrievedChunk[];
  compact?: boolean;
  onOpenDocument: (documentId: string) => void;
}) {
  if (chunks.length === 0) return <p className="text-sm text-muted-foreground">Nothing found.</p>;
  return (
    <ol className="flex flex-col gap-2">
      {chunks.map((chunk, index) => (
        <li key={chunk.id}>
          <button
            type="button"
            onClick={() => onOpenDocument(chunk.document_id)}
            className="flex w-full cursor-pointer flex-col gap-1 rounded-lg border px-3 py-2 text-left hover:bg-muted/50"
          >
            <span className="flex items-center gap-2 text-xs">
              <span className="font-medium tabular-nums text-muted-foreground">#{index + 1}</span>
              <span className="min-w-0 flex-1 truncate font-medium">
                {chunk.title}
                {!compact && chunk.metadata.heading && (
                  <span className="font-normal text-muted-foreground"> · {chunk.metadata.heading}</span>
                )}
              </span>
              {chunk.score !== null && <ScoreBar score={chunk.score} />}
            </span>
            {!compact && <span className="line-clamp-2 text-xs text-muted-foreground">{chunk.text}</span>}
            <RankBadges chunk={chunk} />
          </button>
        </li>
      ))}
    </ol>
  );
}
