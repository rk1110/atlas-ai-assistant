"use client";

import { Activity } from "lucide-react";

import { ActivityItem } from "@/components/chat/activity-item";
import { AgentGraph } from "@/components/chat/agent-graph";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import type { ActivityEntry } from "@/lib/api";
import type { ChatMessage } from "@/lib/use-chat-stream";

/**
 * The Agent Activity Panel: everything the agent did for the latest action request, as a
 * live graph of the agent team (who worked, each handoff, who's working now), then a
 * timeline with timings: memory, routing, every agent step, tool calls with input and
 * output, approvals.
 */
export function ActivityPanel({ messages }: { messages: ChatMessage[] }) {
  const latest = messages.findLast((m) => m.role === "assistant" && m.activity.length > 0);
  const entries = latest?.activity ?? [];
  const startedAt = entries.length ? new Date(entries[0].at).getTime() : 0;
  // Model steps = completed agent steps, minus the non-model ones (memory, routing, handoffs).
  const thinking = entries.filter(
    (e) =>
      e.event.type === "agent_step" &&
      e.event.status === "completed" &&
      !["memory", "router"].includes(e.event.agent) &&
      !e.event.title.startsWith("Handoff"),
  ).length;
  const tools = latest?.toolCalls.length ?? 0;
  const running = latest?.status === "streaming";
  const waitingForYou = latest?.approvals.some((a) => a.state === "pending") ?? false;

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm" disabled={!latest} aria-label="Agent activity">
          <Activity className={running ? "animate-pulse text-primary" : undefined} />
          <span className="hidden sm:inline">Activity</span>
          {tools > 0 && <Badge variant="secondary">{tools}</Badge>}
        </Button>
      </SheetTrigger>
      <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
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
        {latest && (
          <div className="px-4">
            <AgentGraph entries={entries} live={running} waitingForYou={waitingForYou} />
          </div>
        )}
        <ol className="px-4 pb-6">
          {entries.filter((entry) => !isSuperseded(entry, entries)).map((entry, i) => (
            <ActivityItem key={`${i}-${entry.at}`} entry={entry} startedAt={startedAt} />
          ))}
        </ol>
      </SheetContent>
    </Sheet>
  );
}

/** A "started" row is hidden once the same step or tool call has finished: one row per step. */
function isSuperseded(entry: ActivityEntry, entries: ActivityEntry[]): boolean {
  const { event } = entry;
  if (event.type === "agent_step" && event.status === "started") {
    return entries.some((e) => e.event.type === "agent_step" && e.event.step_id === event.step_id && e.event.status !== "started");
  }
  if (event.type === "tool_call" && event.status === "started") {
    return entries.some((e) => e.event.type === "tool_call" && e.event.call_id === event.call_id && e.event.status !== "started");
  }
  return false;
}
