import { ErrorState, PageHeader } from "@nexus/ui";
import { builderBackend } from "@/lib/backend-builder";
import { requireOperator } from "@/lib/session";

import { BuilderTabs } from "../builder-tabs";
import { SectorCatalogView } from "./sector-catalog";

export const metadata = { title: "Pruebas del sector" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T090, 21.1, 54.10): the common battery of each sector — the 12
 * tests every new agent of that sector is born with — with its version.
 * Publishing a new one does not touch the suites that already exist.
 */
export default async function SectorTestsPage() {
  const [operator, sectors] = await Promise.all([
    requireOperator(),
    builderBackend.sectorTests().catch(() => null),
  ]);
  return (
    <>
      <PageHeader
        title="Pruebas del sector"
        description="Las 12 pruebas comunes de cada sector, con su versión. Cada agente nuevo las recibe en la versión vigente del sector de su cliente. Un cliente de «Otro» no tiene batería común."
      />
      <BuilderTabs current="/builder/sector-tests" />
      {sectors === null ? (
        <ErrorState title="No se pudo leer el catálogo de pruebas" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <SectorCatalogView sectors={sectors} operatorId={operator.id} />
      )}
    </>
  );
}
