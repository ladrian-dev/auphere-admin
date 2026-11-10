import { ErrorState, PageHeader } from "@nexus/ui";
import { modelsBackend } from "@/lib/backend-models";

import { RouterTabs } from "../router-tabs";
import { AnomaliesView } from "./anomalies-view";

export const metadata = { title: "Anomalías del router" };
export const dynamic = "force-dynamic";

/** Spec 047 (T150, 40.7, 40.8, 54.9): the last 7 days of every client. */
export default async function RouterAnomaliesPage() {
  const data = await modelsBackend.anomalies().catch(() => null);
  return (
    <>
      <PageHeader
        title="Anomalías del router"
        description="Las decisiones de los últimos 7 días que cayeron en el modelo de reserva o se quedaron sin modelo en la residencia del cliente."
      />
      <RouterTabs current="/router/anomalies" />
      {data === null ? (
        <ErrorState title="No se pudieron leer las anomalías" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <AnomaliesView data={data} />
      )}
    </>
  );
}
