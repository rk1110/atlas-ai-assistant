"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

import { DocumentStatusBadge } from "@/components/knowledge/document-status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { KnowledgeDocument } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  documents: KnowledgeDocument[];
  uploadSource: string;
  onOpen: (documentId: string) => void;
  onDelete: (document: KnowledgeDocument) => void;
}

/** Every document, filterable by source and title. Click a row to see its chunks. */
export function DocumentTable({ documents, uploadSource, onOpen, onDelete }: Props) {
  const [source, setSource] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const sources = [...new Set(documents.map((d) => d.source))].sort();
  const needle = filter.trim().toLowerCase();
  const visible = documents.filter(
    (d) => (source === null || d.source === source) && (!needle || `${d.title} ${d.id}`.toLowerCase().includes(needle)),
  );

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-sm font-medium">Documents</h2>
        <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by title" className="h-8 w-full sm:w-48" aria-label="Filter documents" />
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by source">
        {[null, ...sources].map((s) => (
          <Button key={s ?? "all"} size="xs" variant={source === s ? "default" : "outline"} onClick={() => setSource(s)}>
            {s ?? "All"} · {s === null ? documents.length : documents.filter((d) => d.source === s).length}
          </Button>
        ))}
      </div>
      <ul className="divide-y rounded-lg border">
        {visible.map((doc) => (
          <li key={doc.id} className="flex items-center gap-2 pr-2">
            <button
              type="button"
              onClick={() => onOpen(doc.id)}
              className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 py-2 text-left hover:bg-muted/50"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{doc.title}</span>
                <span className={cn("block truncate text-xs", doc.error ? "text-destructive" : "text-muted-foreground")}>
                  {doc.error ?? doc.id}
                </span>
              </span>
              <span className="hidden shrink-0 text-xs tabular-nums text-muted-foreground sm:block">{doc.chunk_count} chunks</span>
              <DocumentStatusBadge status={doc.status} />
            </button>
            {doc.source === uploadSource && (
              <Button size="icon-sm" variant="ghost" aria-label={`Delete ${doc.title}`} onClick={() => onDelete(doc)}>
                <Trash2 />
              </Button>
            )}
          </li>
        ))}
        {visible.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">No documents match.</li>}
      </ul>
    </section>
  );
}
