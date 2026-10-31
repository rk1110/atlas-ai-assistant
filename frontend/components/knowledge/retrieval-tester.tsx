"use client";

import { Columns3, Search } from "lucide-react";
import { type FormEvent, useState } from "react";

import { ResultList } from "@/components/knowledge/result-list";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, type SearchResponse } from "@/lib/api";
import { COMPARED_STRATEGIES, strategyHint, strategyLabel } from "@/lib/strategies";

type Results = { mode: "single" | "compare"; responses: SearchResponse[] };

/**
 * Type a question, see exactly which passages retrieval returns: the same top-k chunks the
 * chat would put into the prompt. No LLM call, so it's fast and free.
 *
 * "Compare" runs several strategies on the same question side by side: the quickest way to
 * see why hybrid search exists ("What is an MVC?": vector misses it, keyword nails it).
 */
export function RetrievalTester({
  strategies,
  defaultStrategy,
  onOpenDocument,
  onResults,
}: {
  strategies: string[];
  defaultStrategy: string;
  onOpenDocument: (documentId: string) => void;
  /** Chunk ids of the latest single-strategy results, highlighted on the embedding map. */
  onResults: (chunkIds: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [strategy, setStrategy] = useState(defaultStrategy);
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const ready = query.trim().length >= 2 && !searching;

  const run = async (mode: Results["mode"]) => {
    if (!ready) return;
    setSearching(true);
    setError(null);
    try {
      const chosen = mode === "single" ? [strategy] : COMPARED_STRATEGIES.filter((s) => strategies.includes(s));
      const responses = await Promise.all(chosen.map((s) => api.search(query.trim(), s)));
      setResults({ mode, responses });
      onResults(responses[0].chunks.map((c) => c.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run("single");
  };

  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-medium">Test retrieval</h2>
        <p className="text-xs text-muted-foreground">
          What would the chat find for this question? The chat uses <strong>{strategyLabel(defaultStrategy)}</strong>.
        </p>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. What is an MVC at GitLab?" aria-label="Search query" />
        <div className="flex gap-2">
          <Select value={strategy} onValueChange={setStrategy}>
            <SelectTrigger className="w-40" aria-label="Retrieval strategy">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {strategies.map((s) => (
                <SelectItem key={s} value={s}>
                  {strategyLabel(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="submit" variant="outline" disabled={!ready}>
            <Search /> Search
          </Button>
          <Button type="button" variant="outline" disabled={!ready} onClick={() => void run("compare")} title="Run every strategy side by side">
            <Columns3 /> Compare
          </Button>
        </div>
      </form>
      {strategyHint(strategy) && <p className="-mt-1 text-xs text-muted-foreground">{strategyHint(strategy)}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {searching && <p className="text-xs text-muted-foreground">Searching… (the reranker takes a second or two on CPU)</p>}
      {results?.mode === "single" && (
        <ResultList chunks={results.responses[0].chunks} onOpenDocument={onOpenDocument} />
      )}
      {results?.mode === "compare" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results.responses.map((response) => (
            <div key={response.retriever} className="flex flex-col gap-2">
              <h3 className="flex items-baseline justify-between text-xs font-medium" title={strategyHint(response.retriever)}>
                {strategyLabel(response.retriever)}
                <span className="font-normal tabular-nums text-muted-foreground">{response.latency_ms} ms</span>
              </h3>
              <ResultList chunks={response.chunks} compact onOpenDocument={onOpenDocument} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
