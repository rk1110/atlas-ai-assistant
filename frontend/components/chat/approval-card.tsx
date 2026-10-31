"use client";

import { Check, MessageSquare, Pencil, Ticket, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { Approval, ApprovalDecision } from "@/lib/use-chat-stream";

const LONG_FIELDS = new Set(["description", "text"]);

/**
 * Human-in-the-loop: the agent wants to write to another system, and nothing happens until
 * you say so. Shows exactly what will be sent; Edit lets you change it first. The backend
 * re-validates whatever you send against the tool's schema.
 */
export function ApprovalCard({
  approval,
  disabled,
  onRespond,
}: {
  approval: Approval;
  disabled: boolean;
  onRespond: (decision: ApprovalDecision, args?: Record<string, unknown>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>(approval.payload);
  const Icon = approval.tool_name === "post_slack_message" ? MessageSquare : Ticket;
  const pending = approval.state === "pending";

  return (
    <div className="flex flex-col gap-3 rounded-xl border-2 border-primary/30 bg-primary/5 p-4">
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {pending ? "Needs your approval" : "Action"}
          </p>
          <p className="text-sm font-medium">{approval.summary}</p>
        </div>
        {!pending && (
          <Badge variant={approval.state === "rejected" ? "secondary" : "default"}>
            {approval.state === "approved" ? "Approved" : approval.state === "rejected" ? "Rejected" : "Sending…"}
          </Badge>
        )}
      </div>

      <dl className="grid gap-2 text-sm sm:grid-cols-[auto_1fr]">
        {Object.entries(editing ? draft : approval.payload).map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="pt-1.5 text-xs text-muted-foreground capitalize">{key.replaceAll("_", " ")}</dt>
            <dd className="min-w-0">
              {editing ? (
                LONG_FIELDS.has(key) ? (
                  <Textarea value={String(value ?? "")} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} rows={3} />
                ) : (
                  <Input value={String(value ?? "")} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
                )
              ) : (
                <p className="pt-1 break-words whitespace-pre-wrap">{String(value ?? "")}</p>
              )}
            </dd>
          </div>
        ))}
      </dl>

      {pending && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={disabled} onClick={() => onRespond("approve", editing ? draft : undefined)}>
            <Check /> {editing ? "Approve edited" : "Approve"}
          </Button>
          <Button size="sm" variant="outline" disabled={disabled} onClick={() => setEditing(!editing)}>
            <Pencil /> {editing ? "Cancel edit" : "Edit"}
          </Button>
          <Button size="sm" variant="ghost" disabled={disabled} onClick={() => onRespond("reject")}>
            <X /> Reject
          </Button>
        </div>
      )}
    </div>
  );
}
