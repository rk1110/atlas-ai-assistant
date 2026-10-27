/**
 * Liveness probe for Docker's health check. Kept separate from `/` so the check
 * stays cheap and doesn't depend on page rendering or the backend being up.
 */
export function GET(): Response {
  return Response.json({ status: "ok" });
}
