"use client";

import { BarChart3, BookOpen, Inbox, MessageSquare, Network, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const NAV_ITEMS = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/knowledge", label: "Knowledge Base", icon: BookOpen },
  { href: "/graph", label: "Knowledge Graph", icon: Network },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/outbox", label: "Outbox", icon: Inbox },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

/** Client component only because the active highlight needs the current URL (usePathname). */
export function NavMain() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" || pathname.startsWith("/chat") : pathname.startsWith(href);

  return (
    <SidebarGroup>
      <SidebarGroupContent>
        <SidebarMenu>
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
            <SidebarMenuItem key={href}>
              <SidebarMenuButton asChild isActive={isActive(href)} tooltip={label}>
                <Link href={href}>
                  <Icon />
                  <span>{label}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
