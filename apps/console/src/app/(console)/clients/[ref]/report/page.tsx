import { redirect } from "next/navigation";

import { requirePartnerPrincipal } from "@/lib/principal";

/**
 * Spec 083, enmienda del 2026-11-27 (requisito 11.8, D22): la pestaña «Informe»
 * ya no existe; sus cifras viven en Métricas. Un enlace viejo lleva allí con este
 * cliente elegido, y Métricas comprueba sus propios permisos. La guarda de
 * siempre va antes: quien no es partner no aprende nada de la redirección.
 */
export default async function ClientReportRedirect({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  await requirePartnerPrincipal(`/clients/${ref}/report`);
  redirect(`/usage?client=${encodeURIComponent(ref)}`);
}
