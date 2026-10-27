import { BarChart3 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function AnalyticsPage() {
  return (
    <>
      <PageHeader title="Analytics" />
      <PagePlaceholder
        icon={BarChart3}
        phase={3}
        title="Cost, speed and answer quality"
        summary="Every answer already records its tokens, cost and latency. This page will chart them, alongside eval scores over time."
        features={[
          "Cost per question and per model",
          "Latency and time to first token",
          "Eval scores across prompt versions",
          "Thumbs up and down feedback (Phase 7)",
        ]}
      />
    </>
  );
}
