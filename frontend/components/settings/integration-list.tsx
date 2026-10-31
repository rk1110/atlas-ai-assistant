import { Plug } from "lucide-react";
import { connection } from "next/server";

import { Badge } from "@/components/ui/badge";
import { api, type Integration } from "@/lib/api";

/**
 * Connected tools (MCP): the servers Atlas discovered at startup and what each tool may do.
 * "Needs approval" is decided by config/mcp.yaml, never by the server itself.
 */
export async function IntegrationList() {
  await connection();
  let servers: Integration[] | null = null;
  try {
    servers = await api.integrations();
  } catch {
    servers = null;
  }
  if (servers === null) return <p className="mt-4 text-sm text-muted-foreground">Couldn&apos;t reach the backend.</p>;
  return (
    <ul className="mt-4 flex flex-col gap-3">
      {servers.map((server) => (
        <li key={server.name} className="rounded-lg border bg-card p-4 text-sm">
          <p className="flex items-center gap-2">
            <Plug className="size-4 text-muted-foreground" aria-hidden />
            <span className="font-medium capitalize">{server.name}</span>
            <code className="truncate text-xs text-muted-foreground">{server.url}</code>
            <span className={`ml-auto text-xs ${server.status === "connected" ? "text-primary" : "text-destructive"}`}>
              {server.status === "connected" ? "Connected" : server.status}
            </span>
          </p>
          {server.tools.length > 0 ? (
            <ul className="mt-3 flex flex-col gap-1.5">
              {server.tools.map((tool) => (
                <li key={tool.name} className="flex items-center gap-2 text-xs">
                  <code className="font-medium">{tool.name}</code>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">{tool.description}</span>
                  <Badge variant={tool.requires_approval ? "default" : "secondary"}>
                    {tool.requires_approval ? "Needs approval" : "Read-only"}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">No tools: Atlas uses its built-in simulated tools instead.</p>
          )}
        </li>
      ))}
    </ul>
  );
}
