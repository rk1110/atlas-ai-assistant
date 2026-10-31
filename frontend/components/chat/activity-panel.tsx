"use client";

import { Activity } from "lucide-react";

import { ActivityItem } from "@/components/chat/activity-item";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import type { ChatMessage } from "@/lib/use-chat-stream";

/**
 * The Agent Activity Panel: everything the agent did for the latest action request, as a
 * timeline with timings: memory recalled, routing, each "thinking" step, every tool call
 * with its input and output, approvals. Phase 5 adds the animated multi-agent graph.
 */
export function ActivityPanel({ messages }: { messages: ChatMessage[] }) {
  const latest = messages.findLast((m) => m.role === "assistant" && m.activity.length > 0);
  const entries = latest?.activity ?? [];
  const startedAt = entries.length ? new Date(entries[0].at).getTime() : 0;
  const thinking = entries.filter((e) => e.event.type === "agent_step" && e.event.agent === "assistant" && e.event.status === "completed").length;
  const tools = latest?.toolCalls.length ?? 0;
  const running = latest?.status === "streaming";

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm" disabled={!latest} aria-label="Agent activity">
          <Activity className={running ? "animate-pulse text-primary" : undefined} />
          <span className="hidden sm:inline">Activity</span>
          {tools > 0 && <Badge variant="secondary">{tools}</Badge>}
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Agent activity</SheetTitle>
          <SheetDescription>
            {latest
              ? `${thinking} model ${thinking === 1 ? "step" : "steps"}, ${tools} tool ${tools === 1 ? "call" : "calls"}${
                  latest.usage ? `, ${latest.usage.input_tokens + latest.usage.output_tokens} tokens` : ""
                }. Latest action request in this chat.`
              : "Ask Atlas to do something (e.g. open a ticket) to see the agent work."}
          </SheetDescription>
        </SheetHeader>
        <ol className="px-4 pb-6">
          {entries.map((entry, i) => (
            <ActivityItem key={`${i}-${entry.at}`} entry={entry} startedAt={startedAt} />
          ))}
        </ol>
      </SheetContent>
    </Sheet>
  );
}
