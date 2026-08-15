import Link from "next/link";

import { Button, EmptyState, Metric, PageHeader, formatNumber } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

export default async function HomePage() {
  const principal = await requirePrincipal();
  const { t, locale } = await getT(principal.locale);
  const api = backendFor(principal);
  const readClients = can(principal.role, "clients:read");

  // Critical: /me. Best-effort: clients + usage (each degrades to null).
  const [me, clients, usage] = await Promise.all([
    api.me(),
    readClients ? api.listClients({ limit: 200 }).catch(() => null) : null,
    can(principal.role, "usage:read") ? api.usage({ days: 30 }).catch(() => null) : null,
  ]);

  const active = clients?.items.filter((c) => c.status === "active").length ?? null;
  const conversations = usage
    ? Object.entries(usage.totals_by_meter).find(([m]) => m === "channel.message")?.[1] ?? 0
    : null;
  const pending = clients?.items.filter((c) => c.status === "provisioning").length ?? 0;

  return (
    <>
      <PageHeader eyebrow={principal.partnerName} title={t("home.welcome", { name: principal.name })} />
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label={t("home.title")}>
        {readClients ? (
          <Metric
            label={t("home.activeClients")}
            value={active == null ? "—" : formatNumber(active, locale)}
            hint={t("clients.quota", { used: me.quota.used_clients, max: me.quota.max_clients })}
            href="/clients"
          />
        ) : null}
        <Metric
          label={t("home.quota")}
          value={`${formatNumber(me.quota.used_clients, locale)} / ${formatNumber(me.quota.max_clients, locale)}`}
          hint={me.quota.remaining_clients === 0 ? t("clients.quota.full") : undefined}
          href={readClients ? "/clients" : undefined}
        />
        {usage ? (
          <Metric label={t("home.conversations30")} value={formatNumber(conversations, locale)} href="/usage" />
        ) : null}
        {readClients ? (
          <Metric
            label={t("home.pending")}
            value={formatNumber(pending, locale)}
            hint={pending > 0 ? t("home.pending.item", { count: pending }) : t("home.pending.none")}
            href="/clients?status=provisioning"
          />
        ) : null}
      </section>
      {readClients && clients && clients.total === 0 ? (
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
    </>
  );
}
