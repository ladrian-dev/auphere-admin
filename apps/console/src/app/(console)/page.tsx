import Link from "next/link";
import { Suspense } from "react";

import { Alert, AlertDescription, Button, CardSkeleton, EmptyState, Metric, PageHeader, formatNumber } from "@nexus/ui";

import { OnboardingCard } from "@/components/home/onboarding-card";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import type { Home } from "@/lib/backend/home-usage";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Home (CP-08): five actionable figures from ONE call (`GET /console/home`),
 * each block gated by permission on the API and rendered as `null` when
 * absent or failed (partial error → the rest still shows).
 */
export default async function HomePage() {
  const principal = await requirePrincipal();
  const { t, locale } = await getT(principal.locale);
  const api = backendFor(principal);
  const home: Home | null = await api.home().catch(() => null);
  const readClients = can(principal.role, "clients:read");
  const n = (v: number) => formatNumber(v, locale);

  return (
    <>
      <PageHeader eyebrow={principal.partnerName} title={t("home.welcome", { name: principal.name })} />
      <Suspense fallback={<CardSkeleton />}>
        <OnboardingCard principal={principal} />
      </Suspense>
      {home === null ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{t("common.error.backend")}</AlertDescription>
        </Alert>
      ) : null}
      {home && home.errors.length > 0 ? (
        <Alert role="status">
          <AlertDescription>{t("hu.home.partial", { blocks: home.errors.join(", ") })}</AlertDescription>
        </Alert>
      ) : null}
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5" aria-label={t("home.title")}>
        {home?.clients ? (
          <Metric
            label={t("hu.home.clients")}
            value={n(home.clients.active)}
            hint={t("hu.home.clients.hint", { active: n(home.clients.active), total: n(home.clients.total), provisioning: n(home.clients.provisioning) })}
            href="/clients"
          />
        ) : home === null && readClients ? (
          <Metric label={t("hu.home.clients")} value="—" href="/clients" />
        ) : null}
        {home?.conversations_period ? (
          <Metric label={t("hu.home.conversations")} value={n(home.conversations_period.count)} hint={t("hu.home.conversations.hint")} href="/clients" />
        ) : null}
        {home?.usage_units ? (
          <Metric
            label={t("hu.home.usage")}
            value={n(home.usage_units.units)}
            hint={
              home.usage_units.percent != null
                ? t("hu.home.usage.cap", { percent: n(home.usage_units.percent), projected: n(home.usage_units.projected_month_units) })
                : t("hu.home.usage.nocap", { projected: n(home.usage_units.projected_month_units) })
            }
            href="/usage"
          />
        ) : null}
        {home?.agents_with_incidents ? (
          <Metric
            label={t("hu.home.incidents")}
            value={n(home.agents_with_incidents.count)}
            hint={home.agents_with_incidents.count === 0 ? t("hu.home.incidents.none") : t("hu.home.incidents.hint", { count: n(home.agents_with_incidents.count) })}
            href={home.agents_with_incidents.count === 1 ? home.agents_with_incidents.refs[0]!.href : "/clients"}
          />
        ) : null}
        {home?.pending_actions ? (
          <Metric
            label={t("hu.home.pending")}
            value={n(home.pending_actions.count)}
            hint={home.pending_actions.count === 0 ? t("hu.home.pending.none") : undefined}
            href={home.pending_actions.items[0]?.href ?? "/clients"}
          />
        ) : null}
      </section>

      {home?.agents_with_incidents && home.agents_with_incidents.count > 0 ? (
        <section aria-labelledby="incidents-h" className="flex flex-col gap-2">
          <h2 id="incidents-h" className="text-lg font-semibold">
            {t("hu.home.incidents.title")}
          </h2>
          <p className="text-sm text-muted-foreground text-pretty">{t("hu.home.incidents.def")}</p>
          <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
            {home.agents_with_incidents.refs.map((r) => (
              <li key={r.external_client_ref} className="flex min-w-0 flex-col gap-1 px-4 py-3 md:flex-row md:items-baseline md:gap-4">
                <Link href={r.href} className="min-w-0 truncate font-medium hover:underline" title={r.client_name ?? r.external_client_ref}>
                  {r.client_name ?? r.external_client_ref}
                </Link>
                <span className="min-w-0 flex-1 text-sm text-muted-foreground text-pretty">
                  {r.issues
                    .map((i) => (i === "failed_messages_24h" ? t("hu.home.issue.failed_messages_24h", { count: n(r.failed_messages_24h) }) : t(`hu.home.issue.${i}`)))
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {home?.pending_actions && home.pending_actions.count > 0 ? (
        <section aria-labelledby="pending-h" className="flex flex-col gap-2">
          <h2 id="pending-h" className="text-lg font-semibold">
            {t("hu.home.pending.title")}
          </h2>
          <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
            {home.pending_actions.items.map((item, i) => (
              <li key={`${item.kind}-${item.external_client_ref ?? i}`} className="px-4 py-3">
                <Link href={item.href} className="text-sm hover:underline">
                  {item.kind === "client_provisioning"
                    ? t("hu.home.pending.client_provisioning", { client: item.client_name ?? item.external_client_ref ?? "" })
                    : t(`hu.home.pending.${item.kind}`, { count: n(item.count) })}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {readClients && home?.clients && home.clients.total === 0 ? (
        <EmptyState
          title={t("clients.empty.title")}
          description={t("clients.empty.body")}
          action={
            can(principal.role, "clients:write") ? (
              <Button nativeButton={false} render={<Link href="/clients/new" />}>{t("clients.new")}</Button>
            ) : undefined
          }
          readonly={!can(principal.role, "clients:write")}
        />
      ) : null}
      {home ? <p className="font-mono text-xs text-muted-foreground">{t("hu.home.generated", { ms: home.generated_in_ms })}</p> : null}
    </>
  );
}
