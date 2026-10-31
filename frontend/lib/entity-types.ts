/** Colour and label per entity type (backend/graph/schema.py EntityType). */
export const ENTITY_TYPES: Record<string, { color: string; label: string }> = {
  Person: { color: "var(--chart-1)", label: "People" },
  Team: { color: "var(--chart-2)", label: "Teams" },
  Policy: { color: "var(--chart-3)", label: "Policies" },
  System: { color: "var(--chart-4)", label: "Systems" },
  Channel: { color: "var(--chart-5)", label: "Channels" },
  Office: { color: "var(--muted-foreground)", label: "Offices" },
  Company: { color: "var(--foreground)", label: "Company" },
};

export function entityColor(type: string): string {
  return ENTITY_TYPES[type]?.color ?? "var(--muted-foreground)";
}
