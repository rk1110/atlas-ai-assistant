import { Settings } from "lucide-react";
import { connection } from "next/server";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { PagePlaceholder } from "@/components/page-placeholder";
import { MemoryList } from "@/components/settings/memory-list";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ModelsResponse } from "@/lib/api";

/**
 * Settings. The page frame is prerendered; the live model list streams in per request
 * inside <Suspense>. The rest of the controls arrive in Phase 7.
 */
export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" />
      <div className="mx-auto w-full max-w-2xl px-4 pt-12">
        <h2 className="text-lg font-semibold">What Atlas remembers</h2>
        <p className="text-sm text-muted-foreground">
          Lasting facts picked up from your messages and recalled in later chats. Delete anything that&apos;s wrong.
        </p>
        <MemoryList />
        <h2 className="mt-10 text-lg font-semibold">Models</h2>
        <p className="text-sm text-muted-foreground">
          Configured in <code className="font-mono text-xs">config/models.yaml</code>. Pick one in the chat
          header.
        </p>
        <Suspense fallback={<Skeleton className="mt-4 h-64 w-full rounded-lg" />}>
          <ModelList />
        </Suspense>
      </div>
      <PagePlaceholder
        icon={Settings}
        phase={7}
        title="Playground and controls"
        summary="Tune how Atlas answers and compare models side by side."
        features={[
          "Temperature slider per model",
          "Prompt version switcher",
          "Side-by-side model comparison",
          "Per-user cost limits",
        ]}
      />
    </>
  );
}

/** Live availability (keys present, local Ollama running), so it renders per request. */
async function ModelList() {
  await connection();
  let data: ModelsResponse | null = null;
  try {
    data = await api.models();
  } catch {
    data = null;
  }
  return (
    <ul className="mt-4 divide-y rounded-lg border bg-card">
      {data === null && <li className="p-4 text-sm text-muted-foreground">Couldn&apos;t reach the backend.</li>}
      {data?.models.map((m) => (
        <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
          <span className="flex flex-col">
            <span className="font-medium">
              {m.label}
              {m.id === data.default_model && (
                <Badge variant="secondary" className="ml-2">
                  Default
                </Badge>
              )}
            </span>
            <span className="text-xs text-muted-foreground">{m.provider}</span>
          </span>
          <span className={m.available ? "text-primary" : "text-muted-foreground"}>
            {m.available ? "Configured" : m.unavailable_reason}
          </span>
        </li>
      ))}
    </ul>
  );
}
