import { notFound } from "next/navigation";

import { ErrorState } from "@nexus/ui";
import { backend } from "@/lib/backend";
import { leversBackend } from "@/lib/backend-levers";

import { ConsoleV2View } from "./console-v2-view";

export const dynamic = "force-dynamic";

/**
 * Spec 047 (T172; 55.2, 55.4, 55.5): the new console of this partner — which
 * one it sees today, the dry run, the switch and every report. The reports
 * name each client, agent and number themselves.
 */
export default async function PartnerConsoleV2Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [partner, state, reports] = await Promise.all([
    backend.getPartner(id),
    leversBackend.consoleV2State(id).catch(() => null),
    leversBackend.consoleV2Reports(id).catch(() => null),
  ]);
  if (!partner) notFound();
  if (reports === null) {
    return <ErrorState title="No se pudieron leer los informes" description="La API no respondió. Vuelve a intentarlo en un momento." />;
  }
  return <ConsoleV2View partnerId={partner.id} partnerName={partner.name} reports={reports} state={state} />;
}
