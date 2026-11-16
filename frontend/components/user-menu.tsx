"use client";

import { LogOut, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { api, type CurrentUser } from "@/lib/api";

/** Who is logged in, which documents they can read, and Log out (Phase 7). */
export function UserMenu() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const router = useRouter();

  useEffect(() => {
    api.me().then(setUser, () => setUser(null));
  }, []);

  async function logOut() {
    await api.logout().catch(() => undefined); // the cookie is gone either way after this
    router.replace("/login");
    router.refresh(); // drop Server Component output rendered for the old session
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton tooltip={user?.name ?? "Account"}>
              <UserRound />
              <span className="truncate">{user?.name ?? "Account"}</span>
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" className="w-60">
            {user && (
              <>
                <DropdownMenuLabel className="flex flex-col gap-0.5 font-normal">
                  <span className="font-medium">{user.name}</span>
                  <span className="text-xs text-muted-foreground">{user.email}</span>
                  {user.role && <span className="text-xs text-muted-foreground">{user.role}</span>}
                  <span className="text-xs text-muted-foreground">Can read: {user.access_tags.join(", ")}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem onSelect={() => void logOut()}>
              <LogOut /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
