"use client";

import { Square, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { speak, stopSpeaking, useCanSpeak, useSpeakingId } from "@/lib/speech";

/** Read one answer aloud, or stop it. Hidden where the browser has no text-to-speech. */
export function SpeakButton({ id, text }: { id: string; text: string }) {
  const speaking = useSpeakingId() === id;
  if (!useCanSpeak() || !text) return null;
  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      className="size-7 text-muted-foreground"
      onClick={() => (speaking ? stopSpeaking() : speak(id, text))}
      aria-label={speaking ? "Stop reading aloud" : "Read aloud"}
      title={speaking ? "Stop reading aloud" : "Read aloud"}
    >
      {speaking ? <Square className="size-3.5 fill-current" /> : <Volume2 className="size-4" />}
    </Button>
  );
}
