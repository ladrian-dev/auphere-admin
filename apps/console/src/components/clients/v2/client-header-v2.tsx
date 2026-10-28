"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { StatusBadge, buttonVariants, formatDate, tabsListVariants } from "@nexus/ui";

import { CrumbName } from "@/components/shell/crumb-names";
import { clientHref, type ClientTab } from "@/components/shell/routes-v2";
import { ShellBackButton } from "@/components/shell/shell-back-button";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientDetailV2 } from "@/lib/backend/client-records";

import { ClientMenu } from "./client-menu";

const TABS: readonly ClientTab[] = ["panel", "business", "agents"];

/** La pestaña de una ruta: `/clients/x` es el Panel; `/clients/x/business/…`, Negocio. */
export function activeTab(pathname: string, ref: string): ClientTab | null {
  const base = clientHref(ref);
  if (pathname === base) return "panel";
  if (pathname.startsWith(`${base}/business`)) return "business";
  if (pathname.startsWith(`${base}/agents`)) return "agents";
  return null;
}

/**
 * La cabecera de un cliente con la consola nueva, como el prototipo aprobado
 * («Consola de partners v2»): el nombre grande, el nicho y desde cuándo atiende,
 * y debajo la barra de pestañas en vidrio (Panel · Negocio · Agentes, sin número) con
 * «Nuevo agente» a la derecha. Las pestañas son enlaces (`aria-current`), no un
 * `tablist`: cada una es una página con su propia URL. Activo, no lleva
 * insignia ni «⋯» (archivar y borrar están en la lista); en pausa o archivado
 * lo dice y deja sus acciones.
 */
export function ClientHeaderV2({ client, servingSince = null }: { client: ClientDetailV2; servingSince?: string | null }) {
  const t = useT();
  const locale = useLocale();
  const pathname = usePathname() ?? "";
  const ref = client.external_client_ref;
  const current = activeTab(pathname, ref);
  const active = client.lifecycle === "active";
  const tone = client.lifecycle === "archived" ? "muted" : "warn";
  // En la página de un agente (o del nuevo, o de un canal suyo), el título es el
  // agente, como en el prototipo: la ficha solo deja su nombre en las migas.
  if (pathname.startsWith(`${clientHref(ref, "agents")}/`)) return <CrumbName id={ref} label={client.name} />;
  return (
    <header className="grid min-w-0 gap-6" data-slot="client-header-v2">
      {/* Las migas dicen el nombre: la referencia la deriva la consola. */}
      <CrumbName id={ref} label={client.name} />
      <div className="flex min-w-0 items-start justify-between gap-3 border-b border-border pb-6">
        <div className="grid min-w-0 gap-2">
          <div className="flex min-w-0 items-center gap-3">
            <ShellBackButton />
            <h1 className="min-w-0 text-2xl font-semibold tracking-tighter text-balance break-words sm:text-display">{client.name}</h1>
          </div>
          {client.niche || servingSince ? (
            <p className="flex min-w-0 flex-wrap items-center gap-2 text-base text-pretty text-muted-foreground">
              {client.niche ? <span>{client.niche}</span> : null}
              {client.niche && servingSince ? <span aria-hidden="true">·</span> : null}
              {servingSince ? <span className="text-sm">{t("clients.v2.servingSince", { date: formatDate(servingSince, locale) })}</span> : null}
            </p>
          ) : null}
        </div>
        {!active ? (
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge tone={tone}>{t(`clients.v2.lifecycle.${client.lifecycle}` as MessageKey)}</StatusBadge>
            <ClientMenu refId={ref} name={client.name} allowed={client.allowed} detail={client} />
          </div>
        ) : null}
      </div>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <nav aria-label={t("clients.v2.tabs")} className="min-w-0">
          <ul className={tabsListVariants({ floating: true })}>
            {TABS.map((tab) => (
              <li key={tab} className="shrink-0">
                <Link
                  href={clientHref(ref, tab)}
                  aria-current={current === tab ? "page" : undefined}
                  className="inline-flex h-8 items-center gap-2 rounded-full px-3 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-[current=page]:bg-(--tab-on) aria-[current=page]:text-foreground aria-[current=page]:shadow-sm"
                >
                  {t(`clients.v2.tab.${tab}` as MessageKey)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        {client.allowed.includes("new_agent") ? (
          <Link href={`${clientHref(ref, "agents")}/new`} className={buttonVariants()}>
            <Plus aria-hidden="true" />
            {t("agents.new")}
          </Link>
        ) : null}
      </div>
    </header>
  );
}
