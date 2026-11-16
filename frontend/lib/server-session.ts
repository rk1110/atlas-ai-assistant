/**
 * Server side of the login (Phase 7). Imported once by the root layout, which only runs on
 * the server, so `next/headers` never reaches the browser bundle.
 *
 * Server Components call the backend from the frontend container, not from your browser, so
 * the browser's cookie isn't sent automatically: this forwards the incoming request's cookie
 * header. A 401 from the backend means the session expired: go to the login page.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { registerServerSession } from "@/lib/api";

registerServerSession({
  cookieHeader: async () => (await cookies()).toString(),
  onUnauthorized: () => redirect("/login"),
});
