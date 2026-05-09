import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { requireSession } from "@/lib/session";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await requireSession();

  return (
    <SidebarProvider defaultOpen>
      <AppSidebar
        user={{ name: session.user.name, email: session.user.email }}
      />
      <SidebarInset>
        <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b border-border bg-[color:var(--color-bg)]/85 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--color-bg)]/60 px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          {/* Per-page breadcrumbs are rendered by the page itself via
              <PageBreadcrumb /> below the header for tighter layout
              control. Keeping the global header lean. */}
          <div className="flex-1" />
        </header>
        <main className="flex-1 px-4 md:px-8 py-6 md:py-8 max-w-[1400px] w-full mx-auto flex flex-col gap-6">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
