"use client";

import { Button } from "@/components/ui/button";

/** Error boundary for chat pages, e.g. when the backend is down while loading history. */
export default function ChatError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
      <h2 className="text-lg font-semibold">Couldn&apos;t load this conversation</h2>
      <p className="text-sm text-muted-foreground">The Atlas backend may be starting up or unreachable.</p>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
