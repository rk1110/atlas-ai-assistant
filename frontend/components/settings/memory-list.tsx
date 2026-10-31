"use client";

import { Brain, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Memory } from "@/lib/api";

/**
 * What Atlas remembers about you (long-term memory). Facts are picked up from your messages
 * ("I work in the Pune office") and recalled in later chats. You can always see and delete them.
 */
export function MemoryList() {
  const [memories, setMemories] = useState<Memory[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.memories().then(setMemories, (e: unknown) => setError(e instanceof Error ? e.message : "Couldn't load memories"));
  }, []);
  useEffect(load, [load]);

  const forget = async (memory: Memory) => {
    try {
      await api.forgetMemory(memory.id);
      setMemories((prev) => prev?.filter((m) => m.id !== memory.id) ?? null);
      toast.success("Forgotten", { description: memory.content });
    } catch (e) {
      toast.error("Couldn't delete", { description: e instanceof Error ? e.message : undefined });
    }
  };

  if (error) return <p className="mt-4 text-sm text-destructive">{error}</p>;
  if (memories === null) return <Skeleton className="mt-4 h-24 w-full rounded-lg" />;
  if (memories.length === 0) {
    return (
      <p className="mt-4 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        Nothing yet. Tell Atlas something about yourself in chat, like &ldquo;I work in the Pune office&rdquo;.
      </p>
    );
  }
  return (
    <ul className="mt-4 divide-y rounded-lg border bg-card">
      {memories.map((memory) => (
        <li key={memory.id} className="flex items-center gap-3 p-3 text-sm">
          <Brain className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="min-w-0 flex-1">{memory.content}</span>
          <Button variant="ghost" size="icon" onClick={() => forget(memory)} aria-label={`Forget: ${memory.content}`}>
            <Trash2 />
          </Button>
        </li>
      ))}
    </ul>
  );
}
