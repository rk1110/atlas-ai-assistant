import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * 404 for URLs that match no page at all. It renders outside the (main) layout, so without
 * the sidebar; a missing conversation uses app/(main)/not-found.tsx instead.
 */
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-lg font-semibold">Nothing here</h1>
      <p className="text-sm text-muted-foreground">This page doesn&apos;t exist.</p>
      <Button asChild>
        <Link href="/">Go to Atlas</Link>
      </Button>
    </main>
  );
}
