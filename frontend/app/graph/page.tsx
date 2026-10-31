import { Network } from "lucide-react";
import { connection } from "next/server";

import { GraphExplorer } from "@/components/graph/graph-explorer";
import { PageHeader } from "@/components/page-header";
import { api, type GraphSnapshot } from "@/lib/api";

/**
 * Knowledge Graph Explorer. The graph is fetched on the server; if Neo4j isn't running or
 * the graph hasn't been built yet, the page says how to fix that instead of erroring.
 */
export default async function GraphPage() {
  await connection(); // per-request data: never prerender
  let graph: GraphSnapshot | null = null;
  try {
    graph = await api.graph();
  } catch {
    graph = null;
  }
  return (
    <>
      <PageHeader title="Knowledge Graph" />
      {graph && graph.nodes.length > 0 ? (
        <GraphExplorer graph={graph} />
      ) : (
        <div className="mx-auto flex max-w-xl flex-col items-center gap-3 px-4 py-16 text-center">
          <Network className="size-8 text-muted-foreground" />
          <h2 className="text-lg font-medium">{graph ? "The graph is empty" : "The graph database isn't reachable"}</h2>
          <p className="text-sm text-muted-foreground">
            Start Neo4j with <code>docker compose up -d neo4j</code>, then build the graph with{" "}
            <code>docker compose exec backend python -m graph.build</code>.
          </p>
        </div>
      )}
    </>
  );
}
