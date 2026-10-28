import type { Metadata } from "next";

import { LiteBusinessView } from "@/components/lite/lite-business";
import { pageTitle } from "@/i18n/metadata";
import { backendFor } from "@/lib/backend";
import { requireClientPrincipal } from "@/lib/principal";

export const generateMetadata = (): Promise<Metadata> => pageTitle("nav.business");

/**
 * Spec 047 (T168; requisitos 50.1 y 50.4): «Negocio» de la persona del cliente:
 * el horario, las fechas especiales, los servicios y las sedes, con su
 * historial. Solo la persona de un cliente con el módulo `business`. Si la ficha
 * no llega, la pantalla lo dice y deja reintentar (`null`).
 */
export default async function NegocioPage() {
  const principal = await requireClientPrincipal("business", "/negocio");
  const data = await backendFor(principal)
    .liteBusiness()
    .catch(() => null);
  return <LiteBusinessView initial={data} />;
}
