"use client";

import "@xyflow/react/dist/style.css";

import { type Edge, MarkerType, ReactFlow, type ReactFlowInstance } from "@xyflow/react";
import { Bot, Brain, CheckCheck, Compass, Hand, Search, Send, Waypoints, Wrench } from "lucide-react";
import { useTheme } from "next-themes";
import { useMemo } from "react";

import { AgentGraphNode, type AgentFlowNode, type AgentNodeData } from "@/components/chat/agent-graph-node";
import type { ActivityEntry } from "@/lib/api";
import { type GraphNodeId, graphStatus } from "@/lib/agent-graph";
import { useIsClient } from "@/lib/use-is-client";

const NODE_TYPES = { agent: AgentGraphNode };

type Spec = { id: GraphNodeId; label: string; role: string; icon: AgentNodeData["icon"]; x: number; y: number };

// The Phase 5 team. Positions are fixed so the picture is the same every time.
const TEAM: Spec[] = [
  { id: "memory", label: "Memory", role: "recall", icon: Brain, x: 0, y: 0 },
  { id: "router", label: "Router", role: "agent or RAG?", icon: Compass, x: 0, y: 120 },
  { id: "planner", label: "Planner", role: "plans, writes", icon: Waypoints, x: 210, y: 120 },
  { id: "researcher", label: "Researcher", role: "read-only", icon: Search, x: 430, y: 0 },
  { id: "action", label: "Action", role: "tickets, Slack", icon: Send, x: 430, y: 240 },
  { id: "verifier", label: "Verifier", role: "checks answer", icon: CheckCheck, x: 210, y: 290 },
  { id: "tools", label: "Knowledge", role: "search, graph", icon: Wrench, x: 650, y: 0 },
  { id: "systems", label: "Jira / Slack", role: "simulated", icon: Bot, x: 650, y: 190 },
  { id: "you", label: "You", role: "approve", icon: Hand, x: 650, y: 300 },
];
const TEAM_EDGES = [
  "memory>router", "router>planner", "planner>researcher", "researcher>planner", "planner>action",
  "action>planner", "planner>verifier", "verifier>planner", "researcher>tools", "action>tools",
  "action>systems", "action>you",
];

// The Phase 4 single agent (config/agent.yaml mode: single).
const SINGLE: Spec[] = [
  { id: "memory", label: "Memory", role: "recall", icon: Brain, x: 0, y: 0 },
  { id: "router", label: "Router", role: "agent or RAG?", icon: Compass, x: 0, y: 120 },
  { id: "assistant", label: "Agent", role: "all tools", icon: Bot, x: 220, y: 120 },
  { id: "tools", label: "Knowledge", role: "search, graph", icon: Wrench, x: 440, y: 0 },
  { id: "systems", label: "Jira / Slack", role: "simulated", icon: Send, x: 440, y: 140 },
  { id: "you", label: "You", role: "approve", icon: Hand, x: 440, y: 260 },
];
const SINGLE_EDGES = ["memory>router", "router>assistant", "assistant>tools", "assistant>systems", "assistant>you"];

/**
 * The agent team as a live graph: boxes light up as agents work, arrows animate on each
 * handoff, the active agent pulses. Built from the same activity timeline as the list
 * below it, so a reopened chat replays the same picture.
 */
export function AgentGraph({ entries, live, waitingForYou }: { entries: ActivityEntry[]; live: boolean; waitingForYou: boolean }) {
  const { resolvedTheme } = useTheme();
  const isClient = useIsClient();
  const status = useMemo(() => graphStatus(entries, live, waitingForYou), [entries, live, waitingForYou]);
  const single = entries.some((e) => e.event.type === "agent_step" && e.event.agent === "assistant");
  const specs = single ? SINGLE : TEAM;
  const edgeIds = single ? SINGLE_EDGES : TEAM_EDGES;

  const nodes: AgentFlowNode[] = specs.map((s) => ({
    id: s.id,
    type: "agent",
    position: { x: s.x, y: s.y },
    draggable: false,
    data: {
      label: s.label,
      role: s.role,
      icon: s.icon,
      state: status.active === s.id ? "active" : status.visited.has(s.id) ? "visited" : "idle",
    },
  }));
  const edges: Edge[] = edgeIds.map((id) => {
    const [source, target] = id.split(">");
    const used = status.edges.has(id);
    const current = status.lastEdge === id;
    return {
      id,
      source,
      target,
      type: "default",
      animated: current,
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: used ? "var(--primary)" : "var(--border)" },
      style: { stroke: used ? "var(--primary)" : "var(--border)", strokeWidth: current ? 2.5 : used ? 1.5 : 1, opacity: used ? 1 : 0.5 },
    };
  });

  return (
    <div className="h-80 w-full overflow-hidden rounded-lg border bg-muted/20">
      {isClient && (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          colorMode={resolvedTheme === "dark" ? "dark" : "light"}
          fitView
          fitViewOptions={{ padding: 0.08 }}
          // The panel slides in, so the canvas is still growing at first render: fit again
          // once the animation (200 ms) is over.
          onInit={(flow: ReactFlowInstance<AgentFlowNode, Edge>) => setTimeout(() => flow.fitView({ padding: 0.08 }), 260)}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnScroll={false}
          panOnDrag={false}
          proOptions={{ hideAttribution: false }}
        />
      )}
    </div>
  );
}
