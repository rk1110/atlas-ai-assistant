"use client";

import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";

import { DocumentStatusBadge } from "@/components/knowledge/document-status-badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type DocumentDetail } from "@/lib/api";

/**
 * Side panel showing every chunk of one document, in order: exactly the passages that were
 * embedded and that retrieval can return. Useful for spotting bad chunking (cut-off sentences,
 * tiny fragments, pages that became one giant chunk).
 */
export function ChunkViewer({ documentId, onClose }: { documentId: string | null; onClose: () => void }) {
  // Results are stored with the id they belong to, so opening another document shows a
  // skeleton (stale result ignored) without resetting state inside the effect.
  const [loaded, setLoaded] = useState<{ id: string; detail: DocumentDetail | null; error: string | null } | null>(null);

  useEffect(() => {
    if (!documentId) return;
    let active = true;
    api.documentChunks(documentId).then(
      (detail) => active && setLoaded({ id: documentId, detail, error: null }),
      (e: unknown) =>
        active && setLoaded({ id: documentId, detail: null, error: e instanceof Error ? e.message : "Could not load chunks" }),
    );
    return () => {
      active = false;
    };
  }, [documentId]);

  const current = loaded?.id === documentId ? loaded : null;
  const detail = current?.detail ?? null;
  const error = current?.error ?? null;
  const doc = detail?.document;
  return (
    <Sheet open={documentId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-xl">
        <SheetHeader className="border-b">
          <SheetTitle className="pr-6">{doc?.title ?? "Loading…"}</SheetTitle>
          <SheetDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 break-all">
            <span>{documentId}</span>
            {doc && <DocumentStatusBadge status={doc.status} />}
            {doc && <span>{doc.chunk_count} chunks</span>}
            {doc?.url && (
              <a href={doc.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-foreground">
                Open page <ExternalLink className="size-3" />
              </a>
            )}
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-3 overflow-y-auto p-4">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {doc?.error && <p className="text-sm text-destructive">Ingestion failed: {doc.error}</p>}
          {!detail && !error && [0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
          {detail?.chunks.map((chunk) => (
            <article key={chunk.ordinal} className="rounded-lg border">
              <header className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5 text-xs">
                <span className="font-medium tabular-nums">#{chunk.ordinal + 1}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{chunk.heading ?? "(no heading)"}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">{chunk.token_count} tokens</span>
              </header>
              <p className="px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap">{chunk.text}</p>
            </article>
          ))}
          {detail && detail.chunks.length === 0 && !doc?.error && (
            <p className="text-sm text-muted-foreground">No chunks yet.</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
