/**
 * Turns an answer's activity timeline into the state of the agent graph: which agents
 * worked, which handoffs happened, and who is working right now. Pure functions, so the
 * same picture comes from a live stream or from a saved conversation.
 */
import type { ActivityEntry } from "@/lib/api";

export type GraphNodeId =
  | "memory"
  | "router"
  | "planner"
  | "researcher"
  | "action"
  | "verifier"
  | "assistant"
  | "tools"
  | "systems"
  | "you";

export interface GraphStatus {
  visited: Set<GraphNodeId>;
  edges: Set<string>; // "from>to" for every hop that happened
  active: GraphNodeId | null;
  lastEdge: string | null; // the most recent hop: animated
}

const READ_TOOLS = new Set(["search_docs", "query_org_chart", "calculator"]);

export function graphStatus(entries: ActivityEntry[], live: boolean, waitingForYou: boolean): GraphStatus {
  const visited = new Set<GraphNodeId>();
  const edges = new Set<string>();
  let current: GraphNodeId | null = null;
  let lastEdge: string | null = null;

  const hop = (to: GraphNodeId) => {
    visited.add(to);
    if (current && current !== to) {
      lastEdge = `${current}>${to}`;
      edges.add(lastEdge);
    }
    current = to;
  };

  for (const { event } of entries) {
    if (event.type === "agent_step") {
      const agent = event.agent as GraphNodeId;
      if (event.title.startsWith("Handoff to ")) {
        hop("planner");
        hop(event.title.replace("Handoff to ", "") as GraphNodeId);
      } else {
        hop(agent);
      }
    } else if (event.type === "tool_call" && event.status === "started" && current) {
      const target: GraphNodeId = READ_TOOLS.has(event.tool_name) ? "tools" : "systems";
      visited.add(target);
      lastEdge = `${current}>${target}`;
      edges.add(lastEdge);
    } else if (event.type === "approval_request" && current) {
      visited.add("you");
      lastEdge = `${current}>you`;
      edges.add(lastEdge);
    }
  }
  const active: GraphNodeId | null = waitingForYou ? "you" : live ? current : null;
  return { visited, edges, active, lastEdge: live || waitingForYou ? lastEdge : null };
}
