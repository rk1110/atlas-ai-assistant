import { CitationChip } from "@/components/chat/citation-chip";
import type { CitationEvent } from "@/lib/events";

/** The "Sources" row under an answer: one chip per document passage the answer cited. */
export function CitationList({ citations }: { citations: CitationEvent[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-muted-foreground">Sources</span>
      {citations.map((citation) => (
        <CitationChip key={citation.citation_id} citation={citation} />
      ))}
    </div>
  );
}
