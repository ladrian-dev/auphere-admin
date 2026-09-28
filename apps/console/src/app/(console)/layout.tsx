import { SidebarInset, SidebarProvider, SidebarTrigger } from "@nexus/ui";

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
      {/* El shell mide la ventana, no la página: la barra superior y el
          lateral se quedan quietos y **solo el contenido** hace scroll. Con
          `sticky` sobre el scroll del documento la barra se iba con el
          contenido, y además un panel blanco que sube por detrás de la barra
          rompe el marco justo donde tiene que verse. */}
      <SidebarInset className="h-svh min-h-0 overflow-hidden bg-sidebar">
        <header className="flex h-12 shrink-0 items-center gap-2 bg-sidebar px-4">
          {/* The toggle on the left of the bar (owner, 2026-09-24); the partner
              name lives in the user menu. The rest is global: search (⌘K) and
              the notifications bell (CP-07 / CP-29). */}
          <SidebarTrigger className="-ml-1" />
          <div className="flex-1" />
          <ConsoleCommandPalette role={principal.role} />
          <NotificationsBell initialUnread={null} />
        </header>
        {/* El contenido, en blanco, enmarcado por el color del lateral y de
            la barra —que ahora comparten tono y se leen como una sola pieza—.
            Es también el único contenedor que scrollea. */}
        <div className="min-h-0 flex-1 overflow-y-auto rounded-tl-lg border-t border-l border-border bg-card">
          <main
            id="main"
            tabIndex={-1}
            className="mx-auto flex w-full max-w-[1400px] min-w-0 flex-col gap-6 px-4 py-6 outline-none md:px-8 md:py-8"
          >
            {children}
          </main>
        </div>
        {/* The Companion (CO-03): present across the console, never under
            `(auth)`. It is mounted here rather than per page so the drawer
            survives navigation — a run keeps going while the user moves
            around, which is the whole point of the durable run log. */}
        <CompanionLauncher role={principal.role} userId={principal.userId} />
      </SidebarInset>
    </SidebarProvider>
  );
}
