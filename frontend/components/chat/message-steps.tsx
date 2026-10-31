import { CornerDownRight } from "lucide-react";

import type { AgentStepEvent } from "@/lib/events";

/**
 * What Atlas did before answering: a follow-up rewritten into a standalone search (Phase 3),
 * the router handing an action request to the agent, and each "thinking" step of the agent
 * loop (Phase 4). Showing the steps makes a surprising answer explainable.
 */
export function MessageSteps({ steps }: { steps: AgentStepEvent[] }) {
  const done = steps.filter((s) => s.status === "completed");
  if (done.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1">
      {done.map((step) => (
        <li key={step.step_id} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <CornerDownRight className="size-3.5 shrink-0" aria-hidden />
          <span>{step.title}:</span>
          {step.detail && <span className="truncate italic text-foreground/80">{step.detail}</span>}
        </li>
      ))}
    </ul>
  );
}
