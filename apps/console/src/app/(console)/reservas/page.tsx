import type { Metadata } from "next";

import { ReservasView } from "@/components/reservas/reservas-view";
import type { SearchParams } from "@/components/reservas/model/url-state";
import { pageTitle } from "@/i18n/metadata";
import { requireClientPrincipal } from "@/lib/principal";

import { readReservas } from "./read";

export const generateMetadata = (): Promise<Metadata> => pageTitle("nav.reservas");

/**
 * Spec 043 (T022): Reservas, for a client person with the `reservas` module
 * only; anyone else is sent where they belong. The page paints what
 * `readReservas` reads for the URL; spec 082 keeps that first paint on the
 * server and re-reads through `reservasScreenAction`, the same read.
 *
 * `?booking={id}` (the Panel's «Próximas de hoy», T026) opens that booking's
 * panel on arrival, whatever the tab.
 */
export default async function ReservasPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const principal = await requireClientPrincipal("reservas", "/reservas");
  const initial = await readReservas(principal, await searchParams, new Date().toISOString());
  return <ReservasView initial={initial} />;
}
