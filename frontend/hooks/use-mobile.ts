import { useSyncExternalStore } from "react";

const MOBILE_BREAKPOINT = 768;
const QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`;

function subscribe(onChange: () => void): () => void {
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

/**
 * True on phone-sized screens. Rewritten from shadcn's version with useSyncExternalStore,
 * React's built-in way to read browser state, so no setState-in-effect is needed.
 */
export function useIsMobile(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false, // on the server there is no screen: render the desktop layout first
  );
}
