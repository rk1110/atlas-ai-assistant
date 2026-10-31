import { Check, Loader2, Wrench, X } from "lucide-react";

import type { ToolCallEvent } from "@/lib/events";

/**
 * The tools the agent used in this answer, live: a spinner while a tool runs, then a tick
 * (or a cross with the reason). Expand one to see what it returned. This is the agent's
 * work made visible: what it searched, what it looked up, what it did.
 */
export function ToolCallList({ calls }: { calls: ToolCallEvent[] }) {
  if (calls.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1.5" aria-label="Tools used">
      {calls.map((call) => (
        <li key={call.call_id} className="rounded-lg border bg-muted/30 text-xs">
          <details>
            <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2">
              <StatusIcon status={call.status} />
              <span className="min-w-0 flex-1 truncate">{call.summary ?? call.tool_name}</span>
              <code className="shrink-0 text-[10px] text-muted-foreground">{call.tool_name}</code>
            </summary>
            <div className="flex flex-col gap-1 border-t px-3 py-2 text-muted-foreground">
              <p>
                <span className="font-medium text-foreground">Input </span>
                <code className="break-all">{JSON.stringify(call.input)}</code>
              </p>
              {call.error && <p className="text-destructive">{call.error}</p>}
              {call.output !== null && call.output !== undefined && <ToolOutput output={call.output} />}
            </div>
          </details>
        </li>
      ))}
    </ul>
  );
}

function StatusIcon({ status }: { status: ToolCallEvent["status"] }) {
  if (status === "started") return <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" aria-label="Running" />;
  if (status === "failed") return <X className="size-3.5 shrink-0 text-destructive" aria-label="Failed" />;
  return <Check className="size-3.5 shrink-0 text-primary" aria-label="Done" />;
}

function ToolOutput({ output }: { output: unknown }) {
  if (Array.isArray(output)) {
    return (
      <ul className="list-inside list-disc">
        {output.map((item, i) => (
          <li key={i}>{String(item)}</li>
        ))}
      </ul>
    );
  }
  return (
    <p className="flex items-start gap-1">
      <Wrench className="mt-0.5 size-3 shrink-0" aria-hidden />
      <code className="break-all">{JSON.stringify(output)}</code>
    </p>
  );
}
