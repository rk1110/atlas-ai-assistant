import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "@/components/auth/login-form";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Log in · Atlas" };

/**
 * Phase 7: demo email/password login. The accounts are in config/auth.yaml.
 * Static page; the form reads `?next=` in the browser (hence the Suspense boundary).
 */
export default function LoginPage() {
  return (
    <main className="flex min-h-svh items-center justify-center bg-muted/30 p-4">
      <Suspense fallback={<Skeleton className="h-96 w-full max-w-sm rounded-2xl" />}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
