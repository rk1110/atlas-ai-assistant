import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";

import type { DocumentStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const STYLES: Record<DocumentStatus, { label: string; icon: typeof Clock; className: string }> = {
  pending: { label: "Queued", icon: Clock, className: "text-muted-foreground" },
  processing: { label: "Processing", icon: Loader2, className: "text-amber-600 dark:text-amber-400 [&>svg]:animate-spin" },
  ready: { label: "Ready", icon: CheckCircle2, className: "text-emerald-600 dark:text-emerald-400" },
  failed: { label: "Failed", icon: AlertCircle, className: "text-destructive" },
};

/** Where a document is in the ingestion pipeline: queued, processing, ready or failed. */
export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const { label, icon: Icon, className } = STYLES[status];
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap", className)}>
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  );
}
