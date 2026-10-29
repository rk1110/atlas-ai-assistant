"use client";

import type { ReactNode } from "react";

import { useSidebar } from "@/components/ui/sidebar";

/**
 * On phones the sidebar is a sheet over the page, and shadcn's sidebar doesn't close it when
 * you tap a link, so the page you picked stays hidden behind it. This closes the sheet on any
 * link click inside. `contents` keeps the wrapper out of the layout.
 */
export function CloseSidebarOnNavigate({ children }: { children: ReactNode }) {
  const { isMobile, setOpenMobile } = useSidebar();
  return (
    <div
      className="contents"
      onClickCapture={(event) => {
        if (isMobile && event.target instanceof Element && event.target.closest("a[href]")) setOpenMobile(false);
      }}
    >
      {children}
    </div>
  );
}
