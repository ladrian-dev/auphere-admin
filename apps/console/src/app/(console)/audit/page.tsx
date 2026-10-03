import { Download } from "lucide-react";
import { redirect } from "next/navigation";

import { Button, EmptyState, PageHeader } from "@nexus/ui";

import { pageTitle } from "@/i18n/metadata";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { auditQuery, readFilters, type AuditFilterState } from "@/components/audit/audit-query";

import { AuditFilters } from "./filters";
import { AuditTable } from "./audit-table";

export const generateMetadata = () => pageTitle("nav.audit");

type Search = Partial<Record<keyof AuditFilterState, string>>;

/**
 * Spec 029: who did what, on which client, and when — as a timeline by
 * day, with filters chosen from lists and every sentence complete.
 */
export default async function AuditPage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/audit");
  if (!can(principal.role, "audit:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;

  const state = readFilters(sp);
  const query = auditQuery(state, new Date());

  const api = backendFor(principal);
  const [first, options] = await Promise.all([api.auditV2({ limit: 50, ...query, lang: locale }), api.auditFilters(locale)]);
  const people = Object.fromEntries(options.people.map((p) => [p.value, p.label]));
  const categories = Object.fromEntries(options.categories.map((c) => [c.value, c.label]));
  const csv = new URLSearchParams({ ...query, lang: locale });
  const filtered = Object.keys(query).length > 0;

  return (
    <>
      <PageHeader
        eyebrow={t("nav.group.operate")}
        title={t("audit.title")}
        description={t("audit.description")}
        actions={
          <Button nativeButton={false} variant="outline" size="sm" render={<a href={`/api/audit/export?${csv.toString()}`} download />}>
            <Download aria-hidden="true" />
            {t("hu.audit.export")}
          </Button>
        }
      />
      <AuditFilters state={state} options={options} />
      {first.items.length === 0 ? (
        <EmptyState title={filtered ? t("hu.audit.empty.filtered") : t("audit.empty")} readonly />
      ) : (
        <AuditTable key={JSON.stringify(query)} first={first} query={query} people={people} categories={categories} />
      )}
    </>
  );
}
