import { redirect } from "next/navigation";

import { EmptyState, PageHeader, formatDateTime } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { auditActionLabel, auditActionOptions } from "@/components/audit/audit-actions";

import { AuditControls } from "./controls";

export const metadata = { title: "Auditoría" };

type Search = { actor?: string; action?: string; client?: string; cursor?: string; after?: string; before?: string };

export default async function AuditPage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/audit");
  if (!can(principal.role, "audit:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  // Dates arrive as YYYY-MM-DD from the form; the API takes ISO datetimes (UTC day bounds).
  const after = sp.after && /^\d{4}-\d{2}-\d{2}$/.test(sp.after) ? `${sp.after}T00:00:00Z` : undefined;
  const before = sp.before && /^\d{4}-\d{2}-\d{2}$/.test(sp.before) ? `${sp.before}T23:59:59Z` : undefined;
  const api = backendFor(principal);
  const page = await api.auditV2({ limit: 50, actor: sp.actor, action: sp.action, client: sp.client, cursor: sp.cursor, after, before, lang: locale });
  const vocab = await api.auditVocabulary(locale);
  const actionOpts = auditActionOptions(vocab.entries);
  const csv = new URLSearchParams({ lang: locale });
  for (const [k, v] of Object.entries({ actor: sp.actor, action: sp.action, client: sp.client, after, before })) if (v) csv.set(k, v);
  return (
    <>
      <PageHeader eyebrow={t("nav.group.operate")} title={t("audit.title")} description={t("audit.description")} />
      <AuditControls actor={sp.actor ?? ""} action={sp.action ?? ""} after={sp.after ?? ""} before={sp.before ?? ""} nextCursor={page.next_cursor} csvHref={`/api/audit/export?${csv.toString()}`} vocabulary={vocab.entries} />
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
              <span className="shrink-0 text-xs text-muted-foreground">{auditActionLabel(e.action, actionOpts)}</span>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
