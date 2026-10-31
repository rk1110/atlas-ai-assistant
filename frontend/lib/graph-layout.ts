/**
 * Force-directed layout for the knowledge graph (Fruchterman–Reingold).
 *
 * React Flow draws nodes where you tell it; it doesn't place them. This simulation does:
 * every pair of nodes pushes apart (like charges), every edge pulls its two ends together
 * (like a spring), and the "temperature" (how far a node may move per step) cools down
 * until things settle. Connected clusters (a team, its lead, its policies) end up together.
 *
 * Deterministic: the start positions come from the node order, not Math.random(), so the
 * same graph always gets the same picture.
 */

export interface LayoutInput {
  ids: string[];
  edges: { source: string; target: string }[];
}

const WIDTH = 1600;
const HEIGHT = 1100;
const ITERATIONS = 400;
const GRAVITY = 4;

export function forceLayout({ ids, edges }: LayoutInput): Map<string, { x: number; y: number }> {
  const n = ids.length;
  const index = new Map(ids.map((id, i) => [id, i]));
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  ids.forEach((_, i) => {
    // Start on a spiral: spread out, no two nodes on the same spot.
    const angle = i * 2.399963; // the golden angle
    const radius = 40 * Math.sqrt(i + 1);
    x[i] = Math.cos(angle) * radius;
    y[i] = Math.sin(angle) * radius;
  });
  const links = edges
    .map((e) => [index.get(e.source), index.get(e.target)] as const)
    .filter((pair): pair is readonly [number, number] => pair[0] !== undefined && pair[1] !== undefined);

  const k = Math.sqrt((WIDTH * HEIGHT) / Math.max(n, 1)) * 0.75; // ideal edge length
  let temperature = WIDTH / 8;
  const dx = new Float64Array(n);
  const dy = new Float64Array(n);
  for (let step = 0; step < ITERATIONS; step++) {
    dx.fill(0);
    dy.fill(0);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const ddx = x[i] - x[j];
        const ddy = y[i] - y[j];
        const distance = Math.max(Math.hypot(ddx, ddy), 0.01);
        const push = (k * k) / distance;
        dx[i] += (ddx / distance) * push;
        dy[i] += (ddy / distance) * push;
        dx[j] -= (ddx / distance) * push;
        dy[j] -= (ddy / distance) * push;
      }
    }
    for (const [a, b] of links) {
      const ddx = x[a] - x[b];
      const ddy = y[a] - y[b];
      const distance = Math.max(Math.hypot(ddx, ddy), 0.01);
      const pull = (distance * distance) / k;
      dx[a] -= (ddx / distance) * pull;
      dy[a] -= (ddy / distance) * pull;
      dx[b] += (ddx / distance) * pull;
      dy[b] += (ddy / distance) * pull;
    }
    for (let i = 0; i < n; i++) {
      // Gravity: a pull toward the centre that grows with distance. Without it, nodes with no
      // edges (and separate clusters) are only ever pushed apart, and drift so far that "fit
      // view" zooms out until every label is unreadable. Its strength has to balance the
      // combined repulsion of all nodes: 4 keeps ~70 nodes within about +/-450 px.
      dx[i] -= x[i] * GRAVITY;
      dy[i] -= y[i] * GRAVITY;
      const length = Math.max(Math.hypot(dx[i], dy[i]), 0.01);
      x[i] += (dx[i] / length) * Math.min(length, temperature);
      y[i] += (dy[i] / length) * Math.min(length, temperature);
      // Keep everything inside the canvas.
      x[i] = Math.max(-WIDTH / 2, Math.min(WIDTH / 2, x[i]));
      y[i] = Math.max(-HEIGHT / 2, Math.min(HEIGHT / 2, y[i]));
    }
    temperature *= 0.985;
  }
  return new Map(ids.map((id, i) => [id, { x: x[i], y: y[i] }]));
}

/** Same normalisation as the backend's entity_key(): names in facts -> node ids. */
export function entityKey(name: string): string {
  return name.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}
