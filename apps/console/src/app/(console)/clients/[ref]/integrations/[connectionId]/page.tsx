import { notFound, redirect } from "next/navigation";

import { ConnectionPageView } from "@/components/builder/connection-page";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("connPage.title") };
}

/**
 * La página de un conector conectado (spec 047, historia 21; T129; requisito
 * 36.1): la cuenta, el estado con la hora de la última comprobación, los
 * agentes que lo usan con su permiso y sus ajustes, «Reconectar» y
 * «Desconectar para todos». Se llega desde la sección Conectores de un agente
 * (`?agent=` para volver a él) o por su dirección.
 *
 * La conexión es del cliente: cuelga de él, no de un agente. Una conexión de
 * otro cliente es un 404 (la API lo decide). El catálogo del cliente
 * (`GET …/connectors`) dice cómo se autoriza y qué clave pide, para
 * «Reconectar» un conector que no es OAuth; si no llega, la página sigue.
 */
export default async function ConnectionRoute({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string; connectionId: string }>;
  searchParams?: Promise<{ agent?: string }>;
}) {
  const { ref, connectionId } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/integrations/${connectionId}`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if (!can(principal.role, "agents:read")) redirect(`/clients/${encodeURIComponent(ref)}`);
  if (!UUID_RE.test(connectionId)) notFound();

  const api = backendFor(principal);
  const [page, catalog] = await Promise.all([run(() => api.getConnectionPage(ref, connectionId)), run(() => api.listConnectors(ref))]);
  if (!page.ok) {
    if (page.status === 404 || page.status === 422) notFound();
    throw new Error(`connection page ${page.status}`);
  }
  const agent = (await searchParams)?.agent;
  const connector = catalog.ok ? (catalog.data.find((c) => c.slug === page.data.integration) ?? null) : null;
  return (
    <ConnectionPageView
      key={connectionId}
      refId={ref}
      page={page.data}
      connector={connector}
      fromAgent={agent && UUID_RE.test(agent) ? agent : null}
      canWrite={can(principal.role, "agents:write")}
    />
  );
}
