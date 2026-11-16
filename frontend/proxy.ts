import { type NextRequest, NextResponse } from "next/server";

/**
 * Phase 7: send visitors without a session cookie to the login page.
 *
 * Only an *optimistic* check (does the cookie exist?), as the Next.js docs recommend: the
 * proxy runs on every navigation and prefetch, so it mustn't call the backend. The real check,
 * the cookie's signature and expiry, happens in FastAPI on every API call; an expired cookie
 * gets a 401 there, and the app sends you here then.
 */
const SESSION_COOKIE = "atlas_session"; // backend core/auth.py COOKIE_NAME

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname === "/login" || request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const login = new URL("/login", request.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Not for Next's own files, static assets, or route handlers under /api (the container's
  // health check): they're public, requested constantly, or answer for themselves.
  matcher: ["/((?!api/|_next/static|_next/image|favicon.ico|.*\\.(?:png|svg|jpg|ico)$).*)"],
};
