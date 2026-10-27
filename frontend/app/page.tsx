/**
 * Temporary landing page (Phase 1, step 2). It only proves the frontend container runs.
 * Step 6 replaces it with the real app shell (sidebar + chat).
 */
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-zinc-50 dark:bg-zinc-950">
      <h1 className="text-4xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Atlas</h1>
      <p className="text-zinc-500">Frontend is running. The app shell arrives in Phase 1, step 6.</p>
    </main>
  );
}
