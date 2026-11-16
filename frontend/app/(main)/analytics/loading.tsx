import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

/** Shown instantly while the numbers load (also the Suspense boundary for request-time data). */
export default function LoadingAnalytics() {
  return (
    <>
      <PageHeader title="Analytics" />
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <div className="grid gap-8 lg:grid-cols-2">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
        <Skeleton className="h-72" />
      </div>
    </>
  );
}
