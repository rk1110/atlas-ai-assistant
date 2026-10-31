import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

/** Shown instantly while the graph loads (also the Suspense boundary for request-time data). */
export default function LoadingGraph() {
  return (
    <>
      <PageHeader title="Knowledge Graph" />
      <div className="flex flex-1 gap-3 px-4 py-4">
        <Skeleton className="h-[70vh] flex-1" />
        <Skeleton className="hidden h-[70vh] w-80 lg:block" />
      </div>
    </>
  );
}
