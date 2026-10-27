"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { StatusBadge, tabsListVariants } from "@nexus/ui";

import { clientHref, type ClientTab } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
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
 * La cabecera de un cliente con la consola nueva (spec 047, `plan.md` §Ola 2):
 * su nombre y su nicho, su ciclo de vida, el menú ⋯ y las pestañas en píldora
 * Panel · Negocio · Agentes. Las pestañas son enlaces (`aria-current`), no un
 * `tablist`: cada una es una página con su propia URL.
 */
export function ClientHeaderV2({ client }: { client: ClientDetailV2 }) {
  const t = useT();
  const pathname = usePathname() ?? "";
  const current = activeTab(pathname, client.external_client_ref);
  const tone = client.lifecycle === "archived" ? "muted" : client.lifecycle === "paused" ? "warn" : "positive";
  return (
    <header className="grid min-w-0 gap-4" data-slot="client-header-v2">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1">
          <h1 className="text-2xl font-semibold text-balance break-words">{client.name}</h1>
          {client.niche ? <p className="text-sm text-muted-foreground text-pretty">{client.niche}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge tone={tone}>{t(`clients.v2.lifecycle.${client.lifecycle}` as MessageKey)}</StatusBadge>
          <ClientMenu refId={client.external_client_ref} name={client.name} allowed={client.allowed} detail={client} />
        </div>
      </div>
      <nav aria-label={t("clients.v2.tabs")} className="min-w-0">
        <ul className={tabsListVariants()}>
          {TABS.map((tab) => (
            <li key={tab} className="shrink-0">
              <Link
                href={clientHref(client.external_client_ref, tab)}
                aria-current={current === tab ? "page" : undefined}
                className="inline-flex h-8 items-center rounded-full px-3 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-[current=page]:bg-card aria-[current=page]:text-foreground aria-[current=page]:shadow-sm"
              >
                {t(`clients.v2.tab.${tab}` as MessageKey)}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
