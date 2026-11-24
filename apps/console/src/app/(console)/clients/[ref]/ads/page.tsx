import { notFound, redirect } from "next/navigation";

import { AdsReportView } from "@/components/ads/ads-report";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getConsoleVersionCached } from "../data";
import { adsReportAction } from "./actions";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("ads.page.title") };
}

/**
 * «Anuncios» de un cliente con la consola nueva (spec 076, requisito 3): qué
 * anuncios de clic a WhatsApp traen conversaciones y reservas del agente. Cuelga
 * del marco del cliente (Panel · Negocio · Agentes · Anuncios). Con la consola de
 * hoy no existe: vuelve al cliente.
 *
 * Abre con 30 días. Si la lectura falla, el informe lo dice y deja reintentar.
 */
export default async function ClientAdsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/ads`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if (!can(principal.role, "conversations:read")) notFound();
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}`);

  const res = await run(() => backendFor(principal).adsReport(ref, 30));
  if (!res.ok && res.status === 404) notFound();

  return <AdsReportView refId={ref} initial={res.ok ? res.data : null} load={adsReportAction} />;
}
