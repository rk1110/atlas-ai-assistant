"use client";

import { ArrowUp, Check, ImagePlus, Loader2, Mic, Square, X } from "lucide-react";
import { type ClipboardEvent, type DragEvent, type FormEvent, type KeyboardEvent, useCallback, useRef, useState } from "react";

import { ImageThumbnails } from "@/components/chat/image-thumbnails";
import { VoiceWaveform } from "@/components/chat/voice-waveform";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ACCEPTED_IMAGE_TYPES, type AttachedImage, MAX_IMAGES, readImageFile } from "@/lib/images";
import { useVoiceRecorder } from "@/lib/use-voice-recorder";
import { cn } from "@/lib/utils";

interface Props {
  isStreaming: boolean;
  disabled: boolean;
  /** `byVoice`: the question was dictated, so the answer is read aloud too. */
  onSend: (text: string, images: AttachedImage[], byVoice: boolean) => void;
  onStop: () => void;
}

/** Asked when only an image is sent: the backend needs some text to search with. */
const IMAGE_ONLY_QUESTION = "What does this image show?";

/**
 * Message input. Enter sends, Shift+Enter adds a new line, and Stop replaces Send while streaming.
 * Phase 6: attach images with the button, by pasting a screenshot, or by dropping a file;
 * dictate with the mic. The transcript lands in the box to check and edit before sending.
 */
export function Composer({ isStreaming, disabled, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<AttachedImage[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [byVoice, setByVoice] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const textArea = useRef<HTMLTextAreaElement>(null);

  const onTranscript = useCallback((heard: string) => {
    setText((prev) => (prev.trim() ? `${prev.trimEnd()} ${heard}` : heard));
    setByVoice(true);
    textArea.current?.focus();
  }, []);
  const voice = useVoiceRecorder(onTranscript);
  const recording = voice.state === "recording";

  const canSend = (text.trim() !== "" || images.length > 0) && !isStreaming && !disabled && voice.state === "idle";

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend) return;
    onSend(text.trim() || IMAGE_ONLY_QUESTION, images, byVoice);
    setText("");
    setImages([]);
    setProblem(null);
    setByVoice(false);
    voice.clearError();
  }

  async function addFiles(files: File[]) {
    const room = MAX_IMAGES - images.length;
    if (files.length > room) setProblem(`You can attach up to ${MAX_IMAGES} images.`);
    const added: AttachedImage[] = [];
    for (const file of files.slice(0, Math.max(room, 0))) {
      try {
        added.push(await readImageFile(file));
      } catch (error) {
        setProblem(error instanceof Error ? error.message : "Couldn't read that image.");
      }
    }
    if (added.length) setImages((prev) => [...prev, ...added]);
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    // A screenshot copied to the clipboard arrives as a file; plain text pastes as usual.
    const files = Array.from(event.clipboardData.files).filter((f) => f.type.startsWith("image/"));
    if (files.length) {
      event.preventDefault();
      void addFiles(files);
    }
  }

  function onDrop(event: DragEvent<HTMLFormElement>) {
    event.preventDefault();
    setDragging(false);
    void addFiles(Array.from(event.dataTransfer.files));
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // isComposing: don't send while an IME (e.g. Japanese input) is still composing a word.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={submit}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "relative rounded-2xl border bg-card shadow-sm focus-within:ring-2 focus-within:ring-ring/40",
        dragging && "ring-2 ring-primary/50",
      )}
    >
      {recording && <VoiceWaveform levels={voice.levels} seconds={voice.seconds} />}
      <ImageThumbnails
        images={images}
        onRemove={(id) => setImages((prev) => prev.filter((i) => i.id !== id))}
        className="px-4 pt-4"
      />
      <label htmlFor="chat-input" className="sr-only">
        Message Atlas
      </label>
      <Textarea
        id="chat-input"
        ref={textArea}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (!e.target.value) setByVoice(false);
        }}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        placeholder={
          voice.state === "transcribing"
            ? "Transcribing…"
            : recording
              ? "Listening… press ✓ when you're done"
              : images.length
                ? "Ask about your image…"
                : "Ask Atlas anything…"
        }
        rows={1}
        maxLength={8000}
        className="max-h-48 min-h-14 resize-none border-0 bg-transparent py-4 pr-36 pl-4 shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
      {(problem ?? voice.error) && <p className="px-4 pb-2 text-xs text-destructive">{problem ?? voice.error}</p>}
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(",")}
        multiple
        hidden
        onChange={(e) => {
          void addFiles(Array.from(e.target.files ?? []));
          e.target.value = ""; // picking the same file again should still trigger onChange
        }}
      />
      <div className="absolute right-2.5 bottom-2.5 flex gap-1.5">
        {recording ? (
          <>
            <Button type="button" size="icon" variant="ghost" onClick={voice.cancel} aria-label="Discard recording" title="Discard">
              <X />
            </Button>
            <Button type="button" size="icon" variant="secondary" onClick={voice.stop} aria-label="Stop and transcribe" title="Done">
              <Check />
            </Button>
          </>
        ) : (
          voice.supported && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => void voice.start()}
              disabled={isStreaming || voice.state === "transcribing"}
              aria-label="Ask by voice"
              title="Ask by voice (the answer is read aloud)"
            >
              {voice.state === "transcribing" ? <Loader2 className="animate-spin" /> : <Mic />}
            </Button>
          )
        )}
        <Button
          type="button"
          size="icon"
          variant="ghost"
          onClick={() => fileInput.current?.click()}
          disabled={isStreaming || images.length >= MAX_IMAGES}
          aria-label="Attach an image"
          title="Attach an image (or paste a screenshot)"
        >
          <ImagePlus />
        </Button>
        {isStreaming ? (
          <Button type="button" size="icon" variant="secondary" onClick={onStop} aria-label="Stop generating">
            <Square className="fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!canSend} aria-label="Send message">
            <ArrowUp />
          </Button>
        )}
      </div>
    </form>
  );
}
