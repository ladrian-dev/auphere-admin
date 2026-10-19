import { SidebarInset, SidebarProvider, SidebarTrigger } from "@nexus/ui";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { AdminCommandPalette } from "@/components/shell/command-palette";
import { TopBarBreadcrumbs } from "@/components/shell/top-bar-breadcrumbs";
import { backend } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

/**
 * Spec 031: the operator panel's shell, the same frame as the console — the
 * shell measures the window, the bar and the sidebar stay put and only the
 * content scrolls.
 */
export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const operator = await requireOperator();
  // R2.5: open tickets next to their entry. A failed read shows no count
  // rather than a wrong one.
  const openTickets = await backend
    .listTickets({ status: "open" })
    .then((rows) => rows.length)
    .catch(() => 0);

  return (
    <SidebarProvider defaultOpen className="h-svh min-h-0 overflow-hidden">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-sm focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Saltar al contenido
      </a>
      <AppSidebar
        user={{ name: operator.display_name ?? operator.email, email: operator.email, role: operator.role }}
        badges={{ "/tickets": openTickets }}
      />
      <SidebarInset className="min-h-0 overflow-hidden bg-sidebar">
        <header className="flex h-12 shrink-0 items-center gap-2 px-4">
          <SidebarTrigger className="-ml-1" />
          {/* Spec 035: the one breadcrumb of the panel — pages no longer repeat it. */}
          <div className="flex min-w-0 flex-1 items-center">
            <TopBarBreadcrumbs />
          </div>
          <AdminCommandPalette />
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border bg-card">
          <main
            id="main"
            tabIndex={-1}
            className="mx-auto flex w-full max-w-[1400px] min-w-0 flex-col gap-6 px-4 py-6 outline-none md:px-8 md:py-8"
          >
            {children}
          </main>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
