import { ShieldAlert } from "lucide-react";

import type { AgentStepEvent } from "@/lib/events";

/**
 * Phase 7: warnings from the output check (guardrail layer 3), e.g. a link in the answer that
 * no source contains. Shown under the answer, in full, because it's about what you just read.
 */
export function GuardrailWarnings({ steps }: { steps: AgentStepEvent[] }) {
  const warnings = steps.filter((s) => s.agent === "guardrails" && s.status === "failed");
  if (warnings.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {warnings.map((w) => (
        <div
          key={w.step_id}
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200"
        >
          <ShieldAlert className="mt-px size-4 shrink-0" aria-hidden />
          <span>
            <span className="font-medium">{w.title}.</span> {w.detail}
          </span>
        </div>
      ))}
    </div>
  );
}
