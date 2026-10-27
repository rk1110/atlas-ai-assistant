"use client";

import { ArrowUp, Square } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  isStreaming: boolean;
  disabled: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

/** Message input. Enter sends, Shift+Enter adds a new line, and Stop replaces Send while streaming. */
export function Composer({ isStreaming, disabled, onSend, onStop }: Props) {
  const [text, setText] = useState("");

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const message = text.trim();
    if (!message || isStreaming || disabled) return;
    onSend(message);
    setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // isComposing: don't send while an IME (e.g. Japanese input) is still composing a word.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="relative rounded-2xl border bg-card shadow-sm focus-within:ring-2 focus-within:ring-ring/40">
      <label htmlFor="chat-input" className="sr-only">
        Message Atlas
      </label>
      <Textarea
        id="chat-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask Atlas anything…"
        rows={1}
        maxLength={8000}
        className="max-h-48 min-h-14 resize-none border-0 bg-transparent py-4 pr-14 pl-4 shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
      <div className="absolute right-2.5 bottom-2.5">
        {isStreaming ? (
          <Button type="button" size="icon" variant="secondary" onClick={onStop} aria-label="Stop generating">
            <Square className="fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!text.trim() || disabled} aria-label="Send message">
            <ArrowUp />
          </Button>
        )}
      </div>
    </form>
  );
}
