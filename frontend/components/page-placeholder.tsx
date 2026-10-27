import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";

interface Props {
  icon: LucideIcon;
  phase: number;
  title: string;
  summary: string;
  features: string[];
}

/** A "coming in Phase N" page: says what this page will become, so the shell tells the story. */
export function PagePlaceholder({ icon: Icon, phase, title, summary, features }: Props) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-12 sm:py-16">
      <div className="flex size-12 items-center justify-center rounded-xl bg-accent text-accent-foreground">
        <Icon className="size-6" />
      </div>
      <div className="flex flex-col gap-2">
        <Badge variant="secondary" className="w-fit">
          Coming in Phase {phase}
        </Badge>
        <h2 className="text-2xl font-semibold tracking-tight text-balance">{title}</h2>
        <p className="text-muted-foreground">{summary}</p>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2">
        {features.map((feature) => (
          <li key={feature} className="rounded-lg border bg-card p-4 text-sm">
            {feature}
          </li>
        ))}
      </ul>
    </div>
  );
}
