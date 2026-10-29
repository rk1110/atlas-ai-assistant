import { Compass, SquarePen } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { CloseSidebarOnNavigate } from "@/components/close-sidebar-on-navigate";
import { ConversationList } from "@/components/conversation-list";
import { NavMain } from "@/components/nav-main";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarRail,
  SidebarSeparator,
} from "@/components/ui/sidebar";

/**
 * The app's left sidebar. A Server Component: it renders the frame, and only the interactive
 * pieces inside it (NavMain, ConversationList, ThemeToggle) are Client Components.
 */
export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <CloseSidebarOnNavigate>
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <Link href="/">
                  {/* shrink-0: keep the logo square when the sidebar collapses to icons */}
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                    <Compass className="size-4" />
                  </span>
                  <span className="flex flex-col leading-tight group-data-[collapsible=icon]:hidden">
                    <span className="font-semibold">Atlas</span>
                    <span className="text-xs text-muted-foreground">
                      Knowledge assistant
                    </span>
                  </span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              {/* A plain link: "/" always starts a fresh chat. */}
              <SidebarMenuButton asChild tooltip="New chat">
                <Link href="/">
                  <SquarePen />
                  <span>New chat</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          {/* Suspense: these read the current URL, which only exists per request. Next.js
            prerenders everything else and streams these in (Next 16 cacheComponents). */}
          <Suspense fallback={<MenuSkeleton rows={5} />}>
            <NavMain />
          </Suspense>
          <SidebarSeparator />
          <Suspense fallback={<MenuSkeleton rows={4} />}>
            <ConversationList />
          </Suspense>
        </SidebarContent>
        <SidebarFooter>
          <ThemeToggle />
        </SidebarFooter>
        <SidebarRail />
      </CloseSidebarOnNavigate>
    </Sidebar>
  );
}

function MenuSkeleton({ rows }: { rows: number }) {
  return (
    <SidebarMenu className="p-2">
      {Array.from({ length: rows }, (_, i) => (
        <SidebarMenuItem key={i}>
          <SidebarMenuSkeleton />
        </SidebarMenuItem>
      ))}
    </SidebarMenu>
  );
}
