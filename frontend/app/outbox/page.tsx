import { connection } from "next/server";

import { SlackMessageCard } from "@/components/outbox/slack-message-card";
import { TicketCard } from "@/components/outbox/ticket-card";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";

/**
 * Outbox: everything the agent did after you approved it, in the simulated Jira and Slack.
 * Simulated on purpose: the full approve-then-act flow is real, the destination is a table.
 */
export default async function OutboxPage() {
  await connection(); // per-request data: never prerender
  const { tickets, messages } = await api.outbox();
  return (
    <>
      <PageHeader title="Outbox" />
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-4 py-6">
        <p className="text-sm text-muted-foreground">
          Actions the agent took after your approval. Jira and Slack are <strong>simulated</strong> here: nothing leaves
          Atlas. Phase 5 connects them through MCP servers.
        </p>
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium">Jira tickets ({tickets.length})</h2>
          {tickets.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tickets yet. Ask Atlas in chat to open one.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {tickets.map((t) => (
                <TicketCard key={t.key} ticket={t} />
              ))}
            </ul>
          )}
        </section>
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium">Slack messages ({messages.length})</h2>
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No messages yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {messages.map((m) => (
                <SlackMessageCard key={`${m.channel}-${m.created_at}`} message={m} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
