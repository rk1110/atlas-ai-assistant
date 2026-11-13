"use client";

import { useSyncExternalStore } from "react";

/**
 * Reading answers aloud (Phase 6) with the browser's built-in text-to-speech
 * (Web Speech API, `speechSynthesis`): free, instant, works offline, no backend call.
 * The voices are the operating system's, so they sound different on a Mac and on Windows.
 *
 * One answer speaks at a time; `useSpeakingId()` tells each speaker button whether it's on.
 */

let speakingId: string | null = null;
const listeners = new Set<() => void>();

function setSpeaking(id: string | null) {
  speakingId = id;
  listeners.forEach((listener) => listener());
}

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

const noSubscription = () => () => {};

/** canSpeak() for rendering: false on the server, the real answer after hydration (no
 * mismatch between the server HTML and the first client render). */
export function useCanSpeak(): boolean {
  return useSyncExternalStore(noSubscription, canSpeak, () => false);
}

export function speak(id: string, markdown: string): void {
  if (!canSpeak()) return;
  window.speechSynthesis.cancel(); // stop whatever was playing
  const utterance = new SpeechSynthesisUtterance(toSpeakable(markdown));
  utterance.onend = utterance.onerror = () => {
    if (speakingId === id) setSpeaking(null);
  };
  setSpeaking(id);
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (canSpeak()) window.speechSynthesis.cancel();
  setSpeaking(null);
}

export function useSpeakingId(): string | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => speakingId,
    () => null,
  );
}

/**
 * Markdown -> what a person would read out. Without this, the voice says "asterisk asterisk"
 * and "bracket one bracket" for every bold word and citation.
 */
export function toSpeakable(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " (code omitted) ")
    .replace(/\[(\d+)\]|【\d+】/g, "") // citation markers [1] 【1】
    .replace(/!?\[([^\]]+)\]\([^)]+\)/g, "$1") // links and images: keep the text
    .replace(/https?:\/\/\S+/g, "") // bare URLs
    .replace(/^\s{0,3}#{1,6}\s+/gm, "") // headings
    .replace(/^\s*[-*+]\s+/gm, "") // bullets
    .replace(/^\s*\|?[\s:|-]+\|[\s:|-]*$/gm, "") // table separator rows
    .replace(/\|/g, ", ") // table cells
    .replace(/[*_`~]+/g, "") // bold, italics, inline code
    .replace(/\s+/g, " ")
    .trim();
}
