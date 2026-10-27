"use client";

import { MoreHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from "@/components/ui/sidebar";
import { api, CONVERSATIONS_CHANGED, type ConversationSummary, notifyConversationsChanged } from "@/lib/api";

/** Past conversations, most recent first. Refreshes whenever a chat turn finishes. */
export function ConversationList() {
  const pathname = usePathname();
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null);

  useEffect(() => {
    let active = true; // ignore responses that arrive after this component is gone
    const refresh = () => {
      api.conversations().then(
        (list) => {
          if (!active) return;
          setConversations(list);
          setFailed(false);
        },
        () => active && setFailed(true),
      );
    };
    refresh();
    window.addEventListener(CONVERSATIONS_CHANGED, refresh);
    return () => {
      active = false;
      window.removeEventListener(CONVERSATIONS_CHANGED, refresh);
    };
  }, []);

  async function confirmDelete() {
    if (!pendingDelete) return;
    const { id } = pendingDelete;
    setPendingDelete(null);
    try {
      await api.deleteConversation(id);
      toast.success("Conversation deleted");
      notifyConversationsChanged();
      if (pathname === `/chat/${id}`) router.push("/");
    } catch {
      toast.error("Couldn't delete the conversation. Try again.");
    }
  }

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>Recent</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {conversations === null && !failed &&
            Array.from({ length: 4 }, (_, i) => (
              <SidebarMenuItem key={i}>
                <SidebarMenuSkeleton />
              </SidebarMenuItem>
            ))}
          {failed && <p className="px-2 text-xs text-muted-foreground">Couldn&apos;t load conversations.</p>}
          {conversations?.length === 0 && (
            <p className="px-2 text-xs text-muted-foreground">Your conversations will appear here.</p>
          )}
          {conversations?.map((c) => (
            <SidebarMenuItem key={c.id}>
              <SidebarMenuButton asChild isActive={pathname === `/chat/${c.id}`}>
                <Link href={`/chat/${c.id}`} title={c.title ?? "Untitled"}>
                  <span className="truncate">{c.title ?? "Untitled"}</span>
                </Link>
              </SidebarMenuButton>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuAction showOnHover aria-label={`Options for ${c.title ?? "conversation"}`}>
                    <MoreHorizontal />
                  </SidebarMenuAction>
                </DropdownMenuTrigger>
                <DropdownMenuContent side="right" align="start">
                  <DropdownMenuItem variant="destructive" onSelect={() => setPendingDelete(c)}>
                    <Trash2 /> Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>

      <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{pendingDelete?.title ?? "Untitled"}&rdquo; and all its messages will be deleted. This
              can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SidebarGroup>
  );
}
