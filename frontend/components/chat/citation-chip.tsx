"use client";

import { ExternalLink } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { CitationEvent } from "@/lib/events";
import { cn } from "@/lib/utils";

/**
 * A clickable source marker. Opens the exact passage the answer relied on, so the reader can
 * check the claim instead of trusting it. `inline` = the small [1] inside the answer text;
 * otherwise a labelled chip for the "Sources" row.
 */
export function CitationChip({ citation, inline = false }: { citation: CitationEvent; inline?: boolean }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source ${citation.citation_id}: ${citation.title}`}
          className={cn(
            "inline-flex cursor-pointer items-center justify-center gap-1.5 font-medium tabular-nums transition-colors",
            inline
              ? "mx-0.5 h-4.5 min-w-4.5 rounded-full bg-muted px-1 align-text-top text-[10px] leading-none text-muted-foreground hover:bg-primary hover:text-primary-foreground"
              : "h-7 max-w-64 rounded-md border px-2 text-xs hover:bg-muted",
          )}
        >
          {inline ? (
            citation.citation_id
          ) : (
            <>
              <span className="text-muted-foreground">{citation.citation_id}</span>
              <span className="truncate">{citation.title}</span>
            </>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 max-w-[calc(100vw-2rem)]">
        <div className="flex flex-col gap-0.5">
          <p className="font-medium">{citation.title}</p>
          {citation.heading && <p className="text-xs text-muted-foreground">{citation.heading}</p>}
        </div>
        <blockquote className="max-h-60 overflow-y-auto border-l-2 pl-3 text-xs whitespace-pre-wrap text-muted-foreground">
          {citation.snippet}
        </blockquote>
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span className="tabular-nums">{citation.score !== null && `relevance ${citation.score.toFixed(2)}`}</span>
          {citation.url && (
            <a href={citation.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-foreground">
              Open source <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
