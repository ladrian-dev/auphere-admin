import { redirect } from "next/navigation";

import { EmptyState, PageHeader, formatDateTime } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { AuditControls } from "./controls";

export const metadata = { title: "Auditoría" };

type Search = { actor?: string; action?: string; client?: string; cursor?: string };

export default async function AuditPage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/audit");
  if (!can(principal.role, "audit:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const page = await backendFor(principal).audit({ limit: 50, actor: sp.actor, action: sp.action, client: sp.client, cursor: sp.cursor });
  return (
    <>
      <PageHeader eyebrow={t("nav.group.operate")} title={t("audit.title")} description={t("audit.description")} />
      <AuditControls actor={sp.actor ?? ""} action={sp.action ?? ""} nextCursor={page.next_cursor} />
      {page.items.length === 0 ? (
        <EmptyState title={t("audit.empty")} readonly />
      ) : (
        <ol className="divide-y divide-border rounded-md ring-1 ring-foreground/10" aria-label={t("audit.title")}>
          {page.items.map((e) => (
            <li key={e.id} className="flex min-w-0 flex-col gap-1 px-4 py-3 md:flex-row md:items-baseline md:gap-4">
              <time dateTime={e.at} className="shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                {formatDateTime(e.at, locale)}
              </time>
              <span className="min-w-0 flex-1 text-sm text-pretty">{e.summary}</span>
              <span className="shrink-0 font-mono text-xs text-muted-foreground">{e.action}</span>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
