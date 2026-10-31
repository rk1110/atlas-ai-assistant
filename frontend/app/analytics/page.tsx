import { connection } from "next/server";

import { AnalyticsView } from "@/components/analytics/analytics-view";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";

/** Analytics: eval scores over time and chat usage, fetched on the server per request. */
export default async function AnalyticsPage() {
  await connection(); // per-request data: never prerender
  const data = await api.analytics();
  return (
    <>
      <PageHeader title="Analytics" />
      <AnalyticsView data={data} />
    </>
  );
}
