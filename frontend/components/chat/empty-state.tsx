import { Compass } from "lucide-react";

const SUGGESTIONS = [
  "Explain what an LLM token is, with an example",
  "Give me three tips for writing a clear bug report",
  "What's the difference between RAG and fine-tuning?",
  "Draft a short message asking IT to reset my VPN access",
];

/** Shown before the first message. Suggestions double as a quick way to try the app. */
export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center gap-6 py-16 text-center sm:py-24">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
        <Compass className="size-6" />
      </span>
      <div className="flex flex-col gap-1.5">
        <h2 className="text-2xl font-semibold tracking-tight">How can Atlas help?</h2>
        <p className="text-sm text-muted-foreground">
          Company documents arrive in Phase 2. For now, ask general questions.
        </p>
      </div>
      <div className="grid w-full max-w-xl gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="rounded-xl border bg-card px-4 py-3 text-left text-sm transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
