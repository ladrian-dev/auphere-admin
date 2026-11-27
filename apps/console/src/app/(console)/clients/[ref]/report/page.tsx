import { notFound, redirect } from "next/navigation";

import { ClientReport } from "@/components/report/client-report";
import { readPeriod, todayIn } from "@/components/report/report-model";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getClientV2Cached, getConsoleVersionCached } from "../data";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("report.page.title") };
}

/**
 * «Informe» de un cliente con la consola nueva (spec 083): lo que hizo su agente
 * en unas fechas, para enseñarlo o imprimirlo. Cuelga del marco del cliente,
 * después de Anuncios (D1). Con la consola de hoy no existe: vuelve al cliente.
 *
 * Pide leer conversaciones y consumo (1.6). El periodo viaja en la dirección
 * (`?from=&to=`, 1.3): sin él, o si no vale, los últimos 30 días hasta hoy en la
 * zona del cliente (1.4). Si la lectura falla, el informe lo dice y deja reintentar;
 * si falla la lista de clientes, el selector solo trae este.
 */
export default async function ClientReportPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ from?: string | string[]; to?: string | string[] }>;
}) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/report`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if (!can(principal.role, "conversations:read") || !can(principal.role, "usage:read")) notFound();
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}`);

  // El layout ya lo leyó (y dio 404 si no es de este partner): es la misma lectura, en caché.
  const client = await getClientV2Cached(principal, ref);
  const now = new Date();
  const period = readPeriod(await searchParams, client.timezone, now);
  const backend = backendFor(principal);
  const [report, clients] = await Promise.all([
    run(() => backend.clientReport(ref, period.from, period.to)),
    run(() => backend.listClients({ sort: "name", order: "asc", limit: 200 })),
  ]);
  if (!report.ok && report.status === 404) notFound();

  return (
    <ClientReport
      refId={ref}
      clientName={client.name}
      clients={clients.ok ? clients.data.items.map((c) => ({ ref: c.external_client_ref, name: c.name })) : []}
      period={period}
      today={todayIn(client.timezone, now)}
      report={report.ok ? report.data : null}
    />
  );
}
