import { ExternalLink } from "lucide-react";

import type { Usage } from "@/lib/events";

/** Small print under an answer: model, tokens, speed, and a link to its Langfuse trace. */
export function MessageMeta({ usage, traceUrl }: { usage: Usage | null; traceUrl: string | null }) {
  if (!usage && !traceUrl) return null;
  const parts = usage
    ? [
        usage.model_id,
        `${usage.input_tokens} in / ${usage.output_tokens} out tokens`,
        usage.time_to_first_token_ms !== null ? `first token ${(usage.time_to_first_token_ms / 1000).toFixed(1)} s` : null,
        `${(usage.latency_ms / 1000).toFixed(1)} s`,
      ].filter(Boolean)
    : [];
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground tabular-nums">
      {parts.length > 0 && <span>{parts.join(" · ")}</span>}
      {traceUrl && (
        <a href={traceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-foreground">
          View trace <ExternalLink className="size-3" />
        </a>
      )}
    </div>
  );
}
