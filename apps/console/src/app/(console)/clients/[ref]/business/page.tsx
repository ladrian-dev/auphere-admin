import { redirect } from "next/navigation";

import { BusinessSectionsView } from "@/components/business/sections/business-sections";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { callFor } from "@/lib/backend";
import { businessSectionsApi } from "@/lib/backend/business-sections";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getConsoleVersionCached } from "../data";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("business.page.title") };
}

/**
 * «Negocio» de un cliente con la consola nueva (spec 047, T060): datos básicos,
 * sedes, horario, fechas especiales y servicios, cada uno con su estado. Cuelga
 * del marco del cliente (Panel · Negocio · Agentes). Con la consola de hoy no
 * existe: vuelve al cliente.
 *
 * Cada sección se pide por su lado: si una falla, la página pinta las demás y
 * esa dice que no cargó (el estado parcial).
 */
export default async function BusinessPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/business`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}`);

  const api = businessSectionsApi(callFor(principal));
  const [basics, locations, hours, specialDates, services] = await Promise.all([
    run(() => api.getBasics(ref)),
    run(() => api.getLocations(ref)),
    run(() => api.getHours(ref)),
    run(() => api.getSpecialDates(ref)),
    run(() => api.getServices(ref)),
  ]);

  return (
    <BusinessSectionsView
      refId={ref}
      canWrite={can(principal.role, "clients:write")}
      data={{ basics, locations, hours, specialDates, services }}
    />
  );
}
