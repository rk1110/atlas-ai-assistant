import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";

import type { GraphNode } from "@/lib/api";
import { entityColor } from "@/lib/entity-types";

export type EntityNodeData = { entity: GraphNode; state: "normal" | "highlighted" | "dimmed" };
export type EntityFlowNode = Node<EntityNodeData, "entity">;

/**
 * One entity on the graph: a coloured dot sized by how connected it is, and its name.
 * The handles (connection points) are invisible and centred, so edges meet in the middle.
 */
export function EntityNode({ data, selected }: NodeProps<EntityFlowNode>) {
  const { entity, state } = data;
  const size = 10 + Math.min(entity.degree, 16) * 1.5;
  return (
    <div
      className={`flex flex-col items-center gap-1 transition-opacity ${state === "dimmed" ? "opacity-20" : "opacity-100"}`}
      title={entity.description || entity.type}
    >
      <Handle type="target" position={Position.Top} className="!top-1/2 !size-0 !min-h-0 !min-w-0 !border-0 !opacity-0" />
      <span
        className={`rounded-full border-2 ${selected || state === "highlighted" ? "border-foreground" : "border-background"}`}
        style={{ width: size, height: size, background: entityColor(entity.type) }}
      />
      <span
        className={`max-w-36 truncate rounded px-1 text-[11px] leading-tight ${state === "highlighted" || selected ? "bg-background font-semibold" : "text-muted-foreground"}`}
      >
        {entity.name}
      </span>
      <Handle type="source" position={Position.Bottom} className="!top-1/2 !size-0 !min-h-0 !min-w-0 !border-0 !opacity-0" />
    </div>
  );
}
