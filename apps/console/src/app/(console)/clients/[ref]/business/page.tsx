import { redirect } from "next/navigation";

import { BusinessSectionsView } from "@/components/business/sections/business-sections";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { callFor } from "@/lib/backend";
import { businessSectionsApi } from "@/lib/backend/business-sections";
import { clientRecordsApi } from "@/lib/backend/client-records";
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
 * esa dice que no cargó (el estado parcial). Como el prototipo aprobado, también
 * «Documentos y webs» y «Redes sociales».
 *
 * Enmienda del 2026-10-29 (T209, requisitos 57.5 y 60): «Políticas» y
 * «Preguntas frecuentes», y el sector en Datos básicos con los sectores con
 * guía para su selector. El constructor del cliente trabaja solo, al terminar la
 * lectura o al cambiar el sector: sus propuestas llegan como sugerencias de
 * `GET /business` y se deciden en su sección. Sigue sin haber «Completar con el
 * constructor» ni nada que lo nombre (Andrés, 2026-10-28).
 */
export default async function BusinessPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/business`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}`);

  const api = businessSectionsApi(callFor(principal));
  const records = clientRecordsApi(callFor(principal));
  // «Documentos y webs» y «Redes sociales» (como el prototipo): las fuentes y la
  // ficha, que trae las redes guardadas y el estado de cada sección.
  const [basics, locations, hours, specialDates, services, policies, faqs, sectors, sources, record] = await Promise.all([
    run(() => api.getBasics(ref)),
    run(() => api.getLocations(ref)),
    run(() => api.getHours(ref)),
    run(() => api.getSpecialDates(ref)),
    run(() => api.getServices(ref)),
    run(() => api.getPolicies(ref)),
    run(() => api.getFaqs(ref)),
    run(() => api.listSectors()),
    run(() => records.listSources(ref)),
    run(() => records.getBusiness(ref)),
  ]);
  const canWrite = can(principal.role, "clients:write");

  return (
    <div className="grid min-w-0 gap-6">
      <BusinessSectionsView
        refId={ref}
        canWrite={canWrite}
        data={{ basics, locations, hours, specialDates, services, policies, faqs, sectors, sources, record }}
      />
    </div>
  );
}
