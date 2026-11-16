"use client";

import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";

/** Shown when the backend can't be reached while loading the Knowledge Base. */
export default function KnowledgeError({ reset }: { error: Error; reset: () => void }) {
  return (
    <>
      <PageHeader title="Knowledge Base" />
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 px-4 py-16 text-center">
        <p className="font-medium">Couldn&apos;t load the knowledge base.</p>
        <p className="text-sm text-muted-foreground">Check that the backend is running (docker compose ps).</p>
        <Button variant="outline" onClick={reset}>
          Try again
        </Button>
      </div>
    </>
  );
}
