import { Building2 } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button, EmptyState, PageHeader } from "@nexus/ui";

import { ClientsTable } from "@/components/clients/clients-table";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

export const metadata = { title: "Clientes" };

type Search = { q?: string; status?: string; sort?: string; order?: string; page?: string };

export default async function ClientsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/clients");
  if (!can(principal.role, "clients:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const limit = 50;
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  const api = backendFor(principal);
  const [data, me] = await Promise.all([
    api.listClients({
      q: sp.q,
      status: sp.status,
      sort: sp.sort ?? "created_at",
      order: sp.order ?? "desc",
      limit,
      offset: (page - 1) * limit,
    }),
    api.me(),
  ]);
  const canWrite = can(principal.role, "clients:write");
  const quotaFull = me.quota.remaining_clients === 0;
  const filtered = Boolean(sp.q || sp.status);

  return (
    <>
      <PageHeader
        eyebrow={t("nav.clients")}
        title={t("clients.title")}
        description={
          <>
            {t("clients.description")}{" "}
            <span className="font-mono text-sm">{t("clients.quota", { used: me.quota.used_clients, max: me.quota.max_clients })}</span>
          </>
        }
        actions={
          canWrite ? (
            <Button nativeButton={false} render={<Link href="/clients/new" />} disabled={quotaFull} title={quotaFull ? t("clients.quota.full") : undefined}>
              {t("clients.new")}
            </Button>
          ) : undefined
        }
      />
      {quotaFull && canWrite ? (
        <p role="status" className="rounded-md border border-status-warning/40 bg-status-warning/10 px-4 py-3 text-sm">
          {t("clients.quota.full")}
        </p>
      ) : null}
      {data.total === 0 && !filtered ? (
        <EmptyState
          icon={Building2}
          title={t("clients.empty.title")}
          description={t("clients.empty.body")}
          action={canWrite ? <Button nativeButton={false} render={<Link href="/clients/new" />}>{t("clients.new")}</Button> : undefined}
          readonly={!canWrite}
        />
      ) : (
        <ClientsTable
          items={data.items}
          total={data.total}
          page={page}
          limit={limit}
          locale={locale}
          query={{ q: sp.q ?? "", status: sp.status ?? "", sort: sp.sort ?? "created_at", order: sp.order ?? "desc" }}
        />
      )}
    </>
  );
}
