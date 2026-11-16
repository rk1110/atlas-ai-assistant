import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <>
      <PageHeader title="Not found" />
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
        <h2 className="text-lg font-semibold">Nothing here</h2>
        <p className="text-sm text-muted-foreground">This page or conversation doesn&apos;t exist, or it was deleted.</p>
        <Button asChild>
          <Link href="/">Start a new chat</Link>
        </Button>
      </div>
    </>
  );
}
