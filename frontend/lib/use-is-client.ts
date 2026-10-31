import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * false during server rendering and hydration, true after. For widgets that measure the
 * browser (React Flow positions nodes from measured sizes), so the server HTML can't match:
 * render a placeholder first, the real thing once on the client. useSyncExternalStore is
 * the hydration-safe way to tell the two apart (no setState-in-effect).
 */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
