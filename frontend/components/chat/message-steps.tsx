import { CornerDownRight } from "lucide-react";

import type { AgentStepEvent } from "@/lib/events";

/**
 * What Atlas did before answering. Phase 3 has one step: a follow-up question is rewritten
 * into a standalone search ("and for fathers?" → "Parental leave for fathers at Acme"), and
 * showing the rewrite makes a surprising answer explainable. Phase 4 adds agent steps here.
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
