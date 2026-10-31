import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

/** Shown instantly while the outbox loads (also the Suspense boundary for request-time data). */
export default function LoadingOutbox() {
  return (
    <>
      <PageHeader title="Outbox" />
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-3 px-4 py-6">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    </>
  );
}
