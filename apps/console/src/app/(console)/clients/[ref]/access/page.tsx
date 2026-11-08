import { notFound, redirect } from "next/navigation";

import { ClientAccessView } from "@/components/clients/access/client-access-view";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getConsoleVersionCached } from "../data";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("clientAccess.page.title") };
}

/**
 * «Acceso» de un cliente con la consola nueva (spec 056, requisito 3; D3, D4):
 * encender su consola, elegir sus módulos e invitar a sus personas, lo mismo que
 * la pestaña Acceso del panel de Auphere. Es de owner y admin
 * (`client_access:manage`): para los demás roles la página no existe, ni por la
 * barra ni por la dirección (3.2). Cuelga del marco del cliente (Panel · Negocio
 * · Agentes · Acceso). Con la consola de hoy no existe: vuelve al cliente.
 *
 * Si la lectura falla, las dos tarjetas lo dicen y se puede reintentar.
 */
export default async function ClientAccessPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/access`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if (!can(principal.role, "client_access:manage")) notFound();
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}`);

  const res = await run(() => backendFor(principal).clientAccess(ref));
  if (!res.ok && res.status === 404) notFound();

  return <ClientAccessView refId={ref} initial={res.ok ? res.data : null} />;
}
