"use client";

import "@xyflow/react/dist/style.css";

import { Background, Controls, type Edge, ReactFlow } from "@xyflow/react";
import { Search, X } from "lucide-react";
import { useTheme } from "next-themes";
import { type FormEvent, useMemo, useState } from "react";

import { EntityNode, type EntityFlowNode } from "@/components/graph/entity-node";
import { GraphDetails } from "@/components/graph/graph-details";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type GraphFact, type GraphSnapshot } from "@/lib/api";
import { ENTITY_TYPES } from "@/lib/entity-types";
import { entityKey, forceLayout } from "@/lib/graph-layout";
import { useIsClient } from "@/lib/use-is-client";

const NODE_TYPES = { entity: EntityNode };
const EXAMPLES = ["Who leads the team that owns the expense policy?", "Who does Priya Nair report to?"];

/**
 * The Knowledge Graph explorer: every entity Atlas extracted from the Acme documents and how
 * they connect. Ask a question to light up the part of the graph that GraphRAG would use.
 */
export function GraphExplorer({ graph }: { graph: GraphSnapshot }) {
  const { resolvedTheme } = useTheme();
  const isClient = useIsClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [facts, setFacts] = useState<GraphFact[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const nodesById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const positions = useMemo(
    () => forceLayout({ ids: graph.nodes.map((n) => n.id), edges: graph.edges }),
    [graph],
  );

  // What to emphasise: the facts of the last search, else the selected entity's neighbours.
  const focus = useMemo(() => {
    if (facts) {
      const keys = new Set(facts.flatMap((f) => [entityKey(f.source), entityKey(f.target)]));
      const pairs = new Set(facts.map((f) => `${entityKey(f.source)}|${f.relation}|${entityKey(f.target)}`));
      return { nodes: keys, edge: (e: { source: string; target: string; relation: string }) => pairs.has(`${e.source}|${e.relation}|${e.target}`) };
    }
    if (selected) {
      const touching = graph.edges.filter((e) => e.source === selected || e.target === selected);
      return {
        nodes: new Set([selected, ...touching.flatMap((e) => [e.source, e.target])]),
        edge: (e: { source: string; target: string }) => e.source === selected || e.target === selected,
      };
    }
    return null;
  }, [facts, selected, graph.edges]);

  const nodes: EntityFlowNode[] = graph.nodes.map((entity) => ({
    id: entity.id,
    type: "entity",
    position: positions.get(entity.id) ?? { x: 0, y: 0 },
    selected: entity.id === selected,
    data: { entity, state: !focus ? "normal" : focus.nodes.has(entity.id) ? "highlighted" : "dimmed" },
  }));
  const edges: Edge[] = graph.edges.map((e) => {
    const lit = focus?.edge(e) ?? false;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: "straight",
      label: lit ? e.relation.toLowerCase().replaceAll("_", " ") : undefined,
      animated: lit,
      style: { stroke: lit ? "var(--foreground)" : "var(--border)", strokeWidth: lit ? 1.5 : 1, opacity: focus && !lit ? 0.25 : 1 },
      labelStyle: { fontSize: 10, fill: "var(--foreground)" },
      labelBgStyle: { fill: "var(--background)" },
    };
  });

  const search = async (event: FormEvent) => {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setError(null);
    try {
      const result = await api.graphSearch(query.trim());
      setFacts(result.facts);
      setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Graph search failed");
    }
  };

  const clear = () => {
    setFacts(null);
    setQuery("");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 px-4 py-4 lg:flex-row">
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <form onSubmit={search} className="flex gap-2">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={EXAMPLES[0]} aria-label="Ask the graph" />
          <Button type="submit" variant="outline" disabled={query.trim().length < 2}>
            <Search /> Ask
          </Button>
          {facts && (
            <Button type="button" variant="ghost" size="icon" onClick={clear} aria-label="Clear search">
              <X />
            </Button>
          )}
        </form>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="relative h-[70vh] overflow-hidden rounded-lg border">
          {isClient && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            colorMode={resolvedTheme === "dark" ? "dark" : "light"}
            onNodeClick={(_, node) => {
              setFacts(null);
              setSelected(node.id === selected ? null : node.id);
            }}
            onPaneClick={() => setSelected(null)}
            nodesConnectable={false}
            fitView
            minZoom={0.2}
          >
            <Background gap={24} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
          )}
          <ul className="pointer-events-none absolute top-2 left-2 flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-background/80 px-2 py-1 text-[11px] text-muted-foreground">
            {Object.entries(ENTITY_TYPES).map(([type, { color, label }]) => (
              <li key={type} className="flex items-center gap-1">
                <span className="size-2 rounded-full" style={{ background: color }} />
                {label}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-muted-foreground">
          {graph.nodes.length} entities, {graph.edges.length} relations, extracted from the Acme documents by the LLM
          (<code>python -m graph.build</code>). Try: “{EXAMPLES[1]}”
        </p>
      </div>
      <aside className="w-full shrink-0 overflow-y-auto lg:w-80">
        <GraphDetails facts={facts} entity={selected ? (nodesById.get(selected) ?? null) : null} edges={graph.edges} nodes={nodesById} />
      </aside>
    </div>
  );
}
