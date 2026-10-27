import { AlertCircle, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ErrorEvent } from "@/lib/events";

const HINTS: Partial<Record<ErrorEvent["code"], string>> = {
  billing: "Pick another model from the menu at the top right.",
  unavailable: "Pick another model from the menu at the top right.",
  context_too_long: "Start a new chat: this conversation is too long for the model.",
};

/** An error inside an assistant message. "Try again" only appears when retrying can help. */
export function ErrorBanner({ error, onRetry }: { error: ErrorEvent; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm">
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div className="min-w-0 flex-1">
        <p>{error.message}</p>
        {HINTS[error.code] && <p className="text-muted-foreground">{HINTS[error.code]}</p>}
      </div>
      {error.retryable && onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RotateCcw /> Try again
        </Button>
      )}
    </div>
  );
}
