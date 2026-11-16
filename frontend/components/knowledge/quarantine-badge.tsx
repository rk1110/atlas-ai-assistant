import { ShieldAlert } from "lucide-react";

/**
 * Phase 7: chunks the prompt-injection scan held back. They stay visible here, so you can see
 * what was blocked and why, but Atlas never retrieves them.
 */
export function QuarantineBadge({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive"
      title="Suspected prompt injection: these chunks are never used in answers"
    >
      <ShieldAlert className="size-3" aria-hidden />
      {count} quarantined
    </span>
  );
}
