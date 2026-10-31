import { Brain, Check, CircleDot, Loader2, ShieldQuestion, Wrench, X } from "lucide-react";

import type { ActivityEntry } from "@/lib/api";

/** One row of the activity timeline: when, who, what, and (for tools) input and output. */
export function ActivityItem({ entry, startedAt }: { entry: ActivityEntry; startedAt: number }) {
  const seconds = ((new Date(entry.at).getTime() - startedAt) / 1000).toFixed(1);
  const { event } = entry;
  return (
    <li className="relative flex gap-3 pb-4 pl-1">
      <span className="absolute top-6 bottom-0 left-[13px] w-px bg-border" aria-hidden />
      <span className="z-10 flex size-6 shrink-0 items-center justify-center rounded-full border bg-background">
        <Icon entry={entry} />
      </span>
      <div className="min-w-0 flex-1 text-xs">
        <p className="flex items-baseline gap-2">
          <span className="font-medium">{title(entry)}</span>
          <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">+{seconds}s</span>
        </p>
        <p className="text-muted-foreground">
          {event.type === "agent_step" && (event.detail ?? (event.status === "started" ? "Working…" : ""))}
          {event.type === "tool_call" && (event.summary ?? event.tool_name)}
          {event.type === "approval_request" && event.summary}
        </p>
        {event.type === "tool_call" && event.status !== "started" && (
          <details className="mt-1">
            <summary className="cursor-pointer text-muted-foreground">Input and output</summary>
            <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 text-[11px] whitespace-pre-wrap">
              {JSON.stringify({ input: event.input, output: event.output, error: event.error }, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </li>
  );
}

function title(entry: ActivityEntry): string {
  const { event } = entry;
  if (event.type === "agent_step") return `${capitalise(event.agent)} · ${event.title}`;
  if (event.type === "tool_call") return `Tool ${event.tool_name} · ${event.status}`;
  return "Waiting for your approval";
}

function Icon({ entry }: { entry: ActivityEntry }) {
  const { event } = entry;
  if (event.type === "approval_request") return <ShieldQuestion className="size-3.5 text-primary" />;
  if (event.type === "tool_call") {
    if (event.status === "started") return <Loader2 className="size-3.5 text-muted-foreground" />;
    if (event.status === "failed") return <X className="size-3.5 text-destructive" />;
    return <Wrench className="size-3.5 text-primary" />;
  }
  if (event.agent === "assistant") return event.status === "started" ? <CircleDot className="size-3.5 text-muted-foreground" /> : <Brain className="size-3.5 text-primary" />;
  return <Check className="size-3.5 text-primary" />;
}

const capitalise = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
