import type { MapPoint } from "@/lib/api";

/** Hover card for one point on the embedding map. */
export function MapTooltip({ point }: { point: MapPoint }) {
  return (
    <div className="max-w-72 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="font-medium">{point.title}</p>
      {point.heading && <p className="text-muted-foreground">{point.heading}</p>}
      <p className="mt-1 line-clamp-3 text-muted-foreground">{point.preview}</p>
    </div>
  );
}
