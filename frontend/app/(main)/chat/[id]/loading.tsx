import { Skeleton } from "@/components/ui/skeleton";

/** Shown instantly while the conversation loads (Next.js wraps the page in Suspense with this). */
export default function LoadingConversation() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-20">
      <Skeleton className="ml-auto h-10 w-2/5 rounded-2xl" />
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-3/5" />
      </div>
      <Skeleton className="ml-auto h-10 w-1/3 rounded-2xl" />
    </div>
  );
}
