"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * Light/dark/system theme. next-themes sets class="dark" on <html> before the page paints,
 * so there's no white flash when a dark-mode user loads the page.
 */
export function ThemeProvider(props: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props} />;
}
