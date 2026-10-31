/** One stable chart color per knowledge source, so a source looks the same on every chart. */
const KNOWN: Record<string, string> = {
  "gitlab-handbook": "var(--chart-3)",
  "acme-docs": "var(--chart-2)",
  uploads: "var(--chart-5)",
};
const PALETTE = ["var(--chart-1)", "var(--chart-4)", "var(--chart-2)", "var(--chart-3)", "var(--chart-5)"];

export function sourceColor(source: string): string {
  if (KNOWN[source]) return KNOWN[source];
  const hash = [...source].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 0);
  return PALETTE[hash % PALETTE.length];
}
