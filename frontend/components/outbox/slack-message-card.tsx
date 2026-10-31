import { Hash } from "lucide-react";

import type { OutboxMessage } from "@/lib/api";

/** One message posted to the simulated Slack. */
export function SlackMessageCard({ message }: { message: OutboxMessage }) {
  return (
    <li className="flex flex-col gap-1 rounded-lg border px-4 py-3">
      <p className="flex items-center gap-1 text-sm font-medium">
        <Hash className="size-3.5 text-muted-foreground" aria-hidden />
        {message.channel.replace(/^#/, "")}
      </p>
      <p className="text-sm whitespace-pre-wrap">{message.text}</p>
      <p className="text-[11px] text-muted-foreground">Atlas agent · {new Date(message.created_at).toLocaleString()}</p>
    </li>
  );
}
