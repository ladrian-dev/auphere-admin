import { Building2 } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button, EmptyState, PageHeader } from "@nexus/ui";

import { ClientsTable } from "@/components/clients/clients-table";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.clients");

type Search = { q?: string; status?: string; sort?: string; order?: string; page?: string };

export default async function ClientsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/clients");
  if (!can(principal.role, "clients:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const limit = 50;
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  const api = backendFor(principal);
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

  return (
    <>
      <PageHeader
        eyebrow={t("nav.clients")}
        title={t("clients.title")}
        // Sin contador «{used} de {max}»: añadir un cliente no se cobra y no
        // tiene tope (owner, 2026-09-28), así que un contador solo sembraba
        // la duda de si el siguiente cabía.
        description={t("clients.description")}
        actions={
          canWrite ? (
            <Button nativeButton={false} render={<Link href="/clients/new" />}>
              {t("clients.new")}
            </Button>
          ) : undefined
        }
      />
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
