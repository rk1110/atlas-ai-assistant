"use client";

import { Search } from "lucide-react";
import { type FormEvent, useState } from "react";

import { ScoreBar } from "@/components/knowledge/score-bar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type SearchResponse } from "@/lib/api";

/**
 * Type a question, see exactly which passages retrieval returns and how they score: the same
 * top-k chunks the chat would put into the prompt. No LLM call, so it's instant and free.
 */
export function RetrievalTester({ onOpenDocument }: { onOpenDocument: (documentId: string) => void }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const search = async (event: FormEvent) => {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setError(null);
    try {
      setResult(await api.search(query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  };

  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-medium">Test retrieval</h2>
        <p className="text-xs text-muted-foreground">What would the chat find for this question? Higher score = closer in meaning.</p>
      </div>
      <form onSubmit={search} className="flex gap-2">
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. How many vacation days do I get?" aria-label="Search query" />
        <Button type="submit" variant="outline" disabled={searching || query.trim().length < 2}>
          <Search /> Search
        </Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && (
        <ol className="flex flex-col gap-2">
          {result.chunks.map((chunk, index) => (
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
                    {chunk.metadata.heading && <span className="font-normal text-muted-foreground"> · {chunk.metadata.heading}</span>}
                  </span>
                  {chunk.score !== null && <ScoreBar score={chunk.score} />}
                </span>
                <span className="line-clamp-2 text-xs text-muted-foreground">{chunk.text}</span>
              </button>
            </li>
          ))}
          {result.chunks.length === 0 && <li className="text-sm text-muted-foreground">No documents yet.</li>}
        </ol>
      )}
    </section>
  );
}
