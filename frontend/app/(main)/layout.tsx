import { AppSidebar } from "@/components/app-sidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

/**
 * The app's frame: the sidebar plus the page. Every page lives in this `(main)` route group
 * (the parentheses keep "main" out of the URL), except /login (Phase 7), which has no
 * sidebar: there's nobody to list conversations for yet.
 *
 * The sidebar lives in a layout, so it stays mounted (and keeps its state) while you move
 * between pages; only `children` (the page) changes.
 */
export default function MainLayout({ children }: LayoutProps<"/">) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-h-svh">{children}</SidebarInset>
    </SidebarProvider>
  );
}
