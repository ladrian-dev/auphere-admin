import { ErrorState, PageHeader } from "@nexus/ui";
import { builderBackend } from "@/lib/backend-builder";
import { modelsBackend } from "@/lib/backend-models";

import { BuilderTabs } from "../builder-tabs";
import { CalibrationView } from "./calibration-view";
import { RunCalibration } from "./run-calibration";

export const metadata = { title: "Calibración del juez" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T087, 21.8): the judge of the agents' tests gives one verdict per
 * criterion (pass, fail or «No sé»), and it only blocks a publication once it
 * agrees with human labels in Spanish at least 85 % of the time.
 */
export default async function JudgeCalibrationPage({
  searchParams,
}: {
  searchParams: Promise<{ deployment?: string }>;
}) {
  const { deployment } = await searchParams;
  const [reports, deployments] = await Promise.all([
    builderBackend.calibrations().catch(() => null),
    modelsBackend.listDeployments().catch(() => null),
  ]);
  return (
    <>
      <PageHeader
        title="Calibración del juez"
        description="El juez de las pruebas da un veredicto por criterio: pasa, falla o «No sé». No bloquea una publicación hasta coincidir con las etiquetas humanas en español."
        actions={
          <RunCalibration
            deployments={(deployments?.items ?? []).map((d) => ({
              uuid: d.uuid,
              key: d.deployment.id,
              status: d.deployment.status,
            }))}
          />
        }
      />
      <BuilderTabs current="/builder/judge-calibration" />
      {reports === null ? (
        <ErrorState title="No se pudo leer la calibración del juez" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <CalibrationView reports={reports} selected={deployment} />
      )}
    </>
  );
}
