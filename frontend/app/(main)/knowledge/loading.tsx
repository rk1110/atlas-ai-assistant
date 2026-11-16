import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

/** Shown instantly while the document list loads (Next.js wraps the page in Suspense with this). */
export default function LoadingKnowledge() {
  return (
    <>
      <PageHeader title="Knowledge Base" />
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-4 py-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
        <div className="grid gap-8 md:grid-cols-2">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      </div>
    </>
  );
}
