import { Separator, SidebarInset, SidebarProvider, SidebarTrigger } from "@nexus/ui";

import { CompanionLauncher } from "@/components/companion/companion-launcher";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { ConsoleCommandPalette } from "@/components/shell/console-command-palette";
import { NotificationsBell } from "@/components/shell/notifications-bell";
import { getT } from "@/i18n/server";
import { requirePrincipal } from "@/lib/principal";

/**
 * The console shell (CP-07). ``requirePrincipal`` is the real gate: an
 * anonymous visitor goes to /login, a signed-in user with no partner (or a
 * partner not yet enabled) goes to /no-access.
 */
export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const principal = await requirePrincipal();
  const { t } = await getT(principal.locale);
  return (
    <SidebarProvider defaultOpen>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-sm focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        {t("shell.skip")}
      </a>
      <AppSidebar
        partnerName={principal.partnerName}
        partnerSlug={principal.partnerSlug}
        role={principal.role}
        user={{ name: principal.name, email: principal.email }}
      />
      <SidebarInset>
        <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b border-border bg-background/85 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <div className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground" title={principal.partnerName}>
            {principal.partnerName}
          </div>
          {/* lane onboarding: ⌘K + notifications bell (CP-07 / CP-29) */}
          <ConsoleCommandPalette role={principal.role} />
          <NotificationsBell initialUnread={null} />
        </header>
        <main id="main" tabIndex={-1} className="mx-auto flex w-full max-w-[1400px] min-w-0 flex-1 flex-col gap-6 px-4 py-6 outline-none md:px-8 md:py-8">
          {children}
        </main>
        {/* The Companion (CO-03): present across the console, never under
            `(auth)`. It is mounted here rather than per page so the drawer
            survives navigation — a run keeps going while the user moves
            around, which is the whole point of the durable run log. */}
        <CompanionLauncher role={principal.role} userId={principal.userId} />
      </SidebarInset>
    </SidebarProvider>
  );
}
