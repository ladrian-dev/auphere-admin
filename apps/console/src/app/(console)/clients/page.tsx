import { Building2 } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button, EmptyState, ErrorState, PageHeader } from "@nexus/ui";

import { ClientsTable } from "@/components/clients/clients-table";
import { NewClientButton } from "@/components/clients/new-client-button";
import { parseFilter } from "@/components/clients/v2/client-v2-model";
import { ClientsListV2 } from "@/components/clients/v2/clients-list-v2";
import { resolveConsoleVersion } from "@/components/shell/console-version";
import { getT } from "@/i18n/server";
import { backendFor, callFor } from "@/lib/backend";
import { clientRecordsApi } from "@/lib/backend/client-records";
import { can, requirePartnerPrincipal } from "@/lib/principal";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.clients");

type Search = { q?: string; status?: string; sort?: string; order?: string; page?: string; new?: string; filter?: string };

export default async function ClientsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePartnerPrincipal("/clients");
  if (!can(principal.role, "clients:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const limit = 50;
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  const api = backendFor(principal);
  // Spec 047 (T065): con la consola nueva, la lista que dice quién necesita algo.
  if (resolveConsoleVersion(await api.me().catch(() => null)) === "v2") {
    const filter = parseFilter((sp as Search & { filter?: string }).filter);
    const q = (sp.q ?? "").slice(0, 120);
    const list = await clientRecordsApi(callFor(principal))
      .listClientsV2({ q: q || undefined, filter, limit, offset: (page - 1) * limit })
      .catch(() => null);
    return (
      <>
        <PageHeader
          eyebrow={t("nav.clients")}
          title={t("clients.v2.title")}
          description={t("clients.v2.description")}
          actions={can(principal.role, "clients:write") ? <NewClientButton autoOpen={sp.new === "1"} /> : undefined}
        />
        {list ? (
          <ClientsListV2
            items={list.items}
            counts={list.counts ?? { all: list.total, attention: 0, active: 0, archived: 0 }}
            filter={filter}
            q={q}
            total={list.total}
            page={page}
            limit={limit}
          />
        ) : (
          <ErrorState title={t("clients.v2.error")} />
        )}
      </>
    );
  }
  // Ya no se pide `/console/me` aquí: lo único que se leía era la cuota de
  // clientes, y el límite se retiró (owner, 2026-09-28). Una llamada menos
  // por visita a la lista.
  const data = await api.listClients({
    q: sp.q,
    status: sp.status,
    sort: sp.sort ?? "created_at",
    order: sp.order ?? "desc",
    limit,
    offset: (page - 1) * limit,
  });
  const canWrite = can(principal.role, "clients:write");
  const filtered = Boolean(sp.q || sp.status);
  // Spec 047 (T050): con la consola nueva, «Nuevo cliente» es el modal de tres
  // datos; la de hoy sigue con su asistente (`/clients/new`). Lo que no se sabe
  // con certeza pinta la de hoy.
  const v2 = canWrite && resolveConsoleVersion(await api.me().catch(() => null)) === "v2";
  const newClient = v2 ? (
    <NewClientButton autoOpen={sp.new === "1"} />
  ) : (
    <Button nativeButton={false} render={<Link href="/clients/new" />}>
      {t("clients.new")}
    </Button>
  );

  return (
    <>
      <PageHeader
        eyebrow={t("nav.clients")}
        title={t("clients.title")}
        // Sin contador «{used} de {max}»: añadir un cliente no se cobra y no
        // tiene tope (owner, 2026-09-28), así que un contador solo sembraba
        // la duda de si el siguiente cabía.
        description={t("clients.description")}
        actions={canWrite ? newClient : undefined}
      />
      {data.total === 0 && !filtered ? (
        <EmptyState
          icon={Building2}
          title={t("clients.empty.title")}
          description={t("clients.empty.body")}
          action={canWrite && !v2 ? newClient : undefined}
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
