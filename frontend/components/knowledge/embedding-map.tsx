"use client";

import { useEffect, useMemo, useState } from "react";
import { ResponsiveContainer, Scatter, ScatterChart, Tooltip, type TooltipContentProps, XAxis, YAxis, ZAxis } from "recharts";

import { MapTooltip } from "@/components/knowledge/map-tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type EmbeddingMap as MapData, type MapPoint } from "@/lib/api";
import { sourceColor } from "@/lib/source-colors";

/**
 * Every chunk as a dot: its 384-number embedding squashed to 2D with t-SNE (computed by the
 * backend, services/embedding_map.py). Dots close together mean similar things, so topics
 * show up as islands. The latest retrieval test's results are ringed, which shows *where* in
 * meaning-space a question landed. Closeness within a cluster is meaningful; the distance
 * between clusters and the axes are not.
 */
export function EmbeddingMap({
  highlighted,
  onOpenDocument,
}: {
  highlighted: string[];
  onOpenDocument: (documentId: string) => void;
}) {
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.embeddingMap().then(setData, (e: unknown) => setError(e instanceof Error ? e.message : "Map failed to load"));
  }, []);

  const bySource = useMemo(() => {
    const groups = new Map<string, MapPoint[]>();
    for (const point of data?.points ?? []) groups.set(point.source, [...(groups.get(point.source) ?? []), point]);
    return [...groups.entries()];
  }, [data]);
  const hits = useMemo(() => {
    const ids = new Set(highlighted);
    return (data?.points ?? []).filter((p) => ids.has(p.chunk_id));
  }, [data, highlighted]);

  const open = (item: unknown) => {
    const payload = (item as { payload?: MapPoint } | undefined)?.payload;
    if (payload) onOpenDocument(payload.document_id);
  };

  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-medium">Embedding map</h2>
        <p className="text-xs text-muted-foreground">
          {data ? `${data.points.length} chunks, ${data.method} projection. ` : ""}
          Similar passages cluster together. Ringed dots are your last search&apos;s results. Click a dot to open its document.
        </p>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!data && !error && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-80" />
          <p className="text-xs text-muted-foreground">Computing the map (a few seconds the first time)…</p>
        </div>
      )}
      {data && (
        <>
          <div className="h-80 w-full rounded-lg border">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                <XAxis type="number" dataKey="x" hide domain={[-1.05, 1.05]} />
                <YAxis type="number" dataKey="y" hide domain={[-1.05, 1.05]} />
                <ZAxis range={[18, 18]} />
                <Tooltip
                  cursor={false}
                  isAnimationActive={false}
                  content={(props: TooltipContentProps) => {
                    const point = props.payload?.[0]?.payload as MapPoint | undefined;
                    return props.active && point ? <MapTooltip point={point} /> : null;
                  }}
                />
                {bySource.map(([source, points]) => (
                  <Scatter
                    key={source}
                    name={source}
                    data={points}
                    fill={sourceColor(source)}
                    fillOpacity={hits.length ? 0.35 : 0.75}
                    isAnimationActive={false}
                    onClick={open}
                    className="cursor-pointer"
                  />
                ))}
                {hits.length > 0 && (
                  <Scatter
                    name="results"
                    data={hits}
                    fill="var(--primary)"
                    stroke="var(--background)"
                    strokeWidth={2}
                    shape="circle"
                    isAnimationActive={false}
                    onClick={open}
                  />
                )}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            {bySource.map(([source, points]) => (
              <li key={source} className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full" style={{ background: sourceColor(source) }} />
                {source} ({points.length})
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
