import { Ticket } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { OutboxTicket } from "@/lib/api";

/** One ticket in the simulated Jira. */
export function TicketCard({ ticket }: { ticket: OutboxTicket }) {
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border px-4 py-3">
      <div className="flex items-center gap-2 text-sm">
        <Ticket className="size-4 text-muted-foreground" aria-hidden />
        <span className="font-mono font-medium">{ticket.key}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{ticket.summary}</span>
        <Badge variant={ticket.priority === "high" ? "default" : "secondary"}>{ticket.priority}</Badge>
        <Badge variant="outline">{ticket.status}</Badge>
      </div>
      <p className="text-xs whitespace-pre-wrap text-muted-foreground">{ticket.description}</p>
      <p className="text-[11px] text-muted-foreground">{new Date(ticket.created_at).toLocaleString()}</p>
    </li>
  );
}
