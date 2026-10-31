import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import type { LucideIcon } from "lucide-react";

export type AgentNodeData = {
  label: string;
  role: string;
  icon: LucideIcon;
  state: "idle" | "visited" | "active";
};
export type AgentFlowNode = Node<AgentNodeData, "agent">;

/** One agent (or tools, systems, you) on the activity graph. Pulses while it's working. */
export function AgentGraphNode({ data }: NodeProps<AgentFlowNode>) {
  const { icon: Icon, state } = data;
  const tone =
    state === "active"
      ? "border-primary bg-primary text-primary-foreground shadow-lg shadow-primary/30 animate-pulse"
      : state === "visited"
        ? "border-primary/60 bg-primary/10 text-foreground"
        : "border-border bg-background text-muted-foreground opacity-60";
  return (
    <div className={`flex w-36 items-center gap-2 rounded-lg border-2 px-2.5 py-2 text-sm transition-all ${tone}`}>
      <Handle type="target" position={Position.Left} className="!size-0 !min-h-0 !min-w-0 !border-0 !opacity-0" />
      <Icon className="size-4 shrink-0" aria-hidden />
      <span className="flex min-w-0 flex-col leading-tight">
        <span className="truncate font-medium">{data.label}</span>
        <span className={`truncate text-[11px] ${state === "active" ? "opacity-90" : "text-muted-foreground"}`}>{data.role}</span>
      </span>
      <Handle type="source" position={Position.Right} className="!size-0 !min-h-0 !min-w-0 !border-0 !opacity-0" />
    </div>
  );
}
