"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { api } from "@/lib/api";

/** Mirrors voice.max_seconds in config/multimodal.yaml: recording stops by itself here. */
export const MAX_RECORDING_SECONDS = 60;
/** How many bars the waveform shows (the most recent loudness samples). */
const BARS = 32;

const noSubscription = () => () => {};

export type RecorderState = "idle" | "recording" | "transcribing";

/**
 * Record a spoken question and turn it into text (Phase 6).
 *
 * MediaRecorder captures the microphone as compressed audio (webm/opus in Chrome and Firefox,
 * mp4 in Safari); the backend decodes any of them. An AnalyserNode reads the loudness ~16 times
 * a second for the live waveform, so you can see the mic is actually hearing you.
 */
export function useVoiceRecorder(onTranscript: (text: string) => void) {
  const [state, setState] = useState<RecorderState>("idle");
  const [levels, setLevels] = useState<number[]>(() => Array<number>(BARS).fill(0));
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const discardRef = useRef(false);

  const release = useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
  }, []);
  useEffect(() => release, [release]); // leaving the page turns the mic off

  const transcribe = useCallback(
    async (audio: Blob) => {
      setState("transcribing");
      try {
        const transcript = await api.transcribe(audio);
        if (transcript.text) onTranscript(transcript.text);
        else setError("I didn't catch any words. Try again a little closer to the mic.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Couldn't transcribe the recording.");
      } finally {
        setState("idle");
      }
    },
    [onTranscript],
  );

  const start = useCallback(async () => {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access was blocked. Allow it in the browser's address bar.");
      return;
    }
    const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg"].find((t) => MediaRecorder.isTypeSupported(t));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = () => {
      release();
      if (discardRef.current) setState("idle");
      else void transcribe(new Blob(chunks, { type: recorder.mimeType }));
    };

    // Loudness for the waveform: root mean square of the latest samples, scaled to 0..1.
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      analyser.getByteTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, v) => sum + ((v - 128) / 128) ** 2, 0) / samples.length);
      setLevels((prev) => [...prev.slice(1), Math.min(1, rms * 4)]);
      const elapsed = (Date.now() - startedAt) / 1000;
      setSeconds(elapsed);
      if (elapsed >= MAX_RECORDING_SECONDS && recorder.state === "recording") recorder.stop();
    }, 60);

    cleanupRef.current = () => {
      window.clearInterval(timer);
      stream.getTracks().forEach((track) => track.stop()); // the browser's "mic in use" dot goes away
      void context.close();
    };
    recorderRef.current = recorder;
    discardRef.current = false;
    setLevels(Array<number>(BARS).fill(0));
    setSeconds(0);
    recorder.start();
    setState("recording");
  }, [release, transcribe]);

  /** Stop and transcribe. */
  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  /** Stop and throw the recording away. */
  const cancel = useCallback(() => {
    discardRef.current = true;
    stop();
  }, [stop]);

  // false on the server and during hydration, so the mic button doesn't cause a mismatch.
  const supported = useSyncExternalStore(
    noSubscription,
    () => "MediaRecorder" in window && !!navigator.mediaDevices,
    () => false,
  );

  return { state, levels, seconds, error, supported, start, stop, cancel, clearError: () => setError(null) };
}
