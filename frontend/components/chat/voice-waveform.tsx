"use client";

import { MAX_RECORDING_SECONDS } from "@/lib/use-voice-recorder";

/** Live loudness bars while recording, newest on the right, plus the elapsed time. */
export function VoiceWaveform({ levels, seconds }: { levels: number[]; seconds: number }) {
  const left = Math.max(0, Math.ceil(MAX_RECORDING_SECONDS - seconds));
  return (
    <div className="flex items-center gap-3 px-4 pt-4" role="status" aria-label="Recording">
      <span className="size-2.5 shrink-0 animate-pulse rounded-full bg-red-500" aria-hidden />
      <div className="flex h-8 flex-1 items-center gap-[3px]" aria-hidden>
        {levels.map((level, i) => (
          <span
            key={i}
            className="w-1 flex-1 rounded-full bg-primary/70 transition-[height] duration-75"
            style={{ height: `${Math.max(8, level * 100)}%` }}
          />
        ))}
      </div>
      <span className="w-20 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
        {formatSeconds(seconds)}
        {left <= 10 && ` · ${left}s left`}
      </span>
    </div>
  );
}

function formatSeconds(seconds: number): string {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
