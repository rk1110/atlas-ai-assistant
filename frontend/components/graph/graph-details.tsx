import { FileText } from "lucide-react";

import type { GraphEdge, GraphFact, GraphNode } from "@/lib/api";
import { entityColor } from "@/lib/entity-types";

const verb = (relation: string) => relation.toLowerCase().replaceAll("_", " ");

/**
 * The side panel: either the facts a graph search found (what GraphRAG would hand the
 * model), or one selected entity's connections. Every fact shows the sentence it came from
 * and its document: graph answers are cited like any other.
 */
export function GraphDetails({
  facts,
  entity,
  edges,
  nodes,
}: {
  facts: GraphFact[] | null;
  entity: GraphNode | null;
  edges: GraphEdge[];
  nodes: Map<string, GraphNode>;
}) {
  if (facts) {
    return (
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{facts.length} facts found</h3>
        <p className="text-xs text-muted-foreground">
          What hybrid + graph search adds to the prompt, nearest first. Hop 2 = connected through another entity.
        </p>
        <ul className="flex flex-col gap-2">
          {facts.map((f) => (
            <li key={`${f.source}-${f.relation}-${f.target}`} className="rounded-lg border px-3 py-2 text-xs">
              <p>
                <strong>{f.source}</strong> {verb(f.relation)} <strong>{f.target}</strong>
                <span className="ml-1 text-muted-foreground">· hop {f.hops}</span>
              </p>
              <p className="mt-1 italic text-muted-foreground">“{f.evidence}”</p>
              <p className="mt-1 flex items-center gap-1 text-muted-foreground">
                <FileText className="size-3" /> {f.document_title}
              </p>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (!entity) {
    return (
      <p className="text-sm text-muted-foreground">
        Click an entity to see its connections, or ask a question above to see what graph search finds.
      </p>
    );
  }
  const connected = edges.filter((e) => e.source === entity.id || e.target === entity.id);
  return (
    <div className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <span className="size-2.5 rounded-full" style={{ background: entityColor(entity.type) }} />
        {entity.name}
      </h3>
      <p className="text-xs text-muted-foreground">
        {entity.type}
        {entity.description && ` · ${entity.description}`} · mentioned in {entity.sources.length} document
        {entity.sources.length === 1 ? "" : "s"}
      </p>
      <ul className="flex flex-col gap-2">
        {connected.map((e) => (
          <li key={e.id} className="rounded-lg border px-3 py-2 text-xs">
            <p>
              <strong>{nodes.get(e.source)?.name ?? e.source}</strong> {verb(e.relation)}{" "}
              <strong>{nodes.get(e.target)?.name ?? e.target}</strong>
            </p>
            <p className="mt-1 italic text-muted-foreground">“{e.evidence}”</p>
            <p className="mt-1 truncate text-muted-foreground">{e.document_id}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
