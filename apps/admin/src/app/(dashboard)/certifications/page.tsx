import { Button, Callout, ErrorState, Input, Label, NativeSelect, PageHeader } from "@nexus/ui";
import { modelsBackend } from "@/lib/backend-models";

import { CertificationsView } from "./certifications-view";
import { RunCertification } from "./run-certification";

export const metadata = { title: "Certificaciones" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T150, historia 24, 42.7, 54.3): no model speaks to a client
 * without having shown it does the job in Spanish. By deployment (the common
 * battery, per task) and by agent (its own suite).
 */
export default async function CertificationsPage({
  searchParams,
}: {
  searchParams: Promise<{ deployment?: string; task?: string }>;
}) {
  const { deployment, task } = await searchParams;
  const [data, taxonomy, deployments, batteries] = await Promise.all([
    modelsBackend.certifications({ deployment: deployment || undefined, task: task || undefined }).catch(() => null),
    modelsBackend.taxonomy().catch(() => null),
    modelsBackend.listDeployments().catch(() => null),
    modelsBackend.batteries().catch(() => null),
  ]);
  const tasks = taxonomy?.tasks.map((t) => t.code) ?? [];
  const battery = batteries?.items[0];
  return (
    <>
      <PageHeader
        title="Certificaciones"
        description="Ningún modelo habla con un cliente sin haber pasado antes la batería común en español de su tarea y, en conversación, la suite de ese agente."
        actions={
          <RunCertification
            deployments={(deployments?.items ?? []).map((d) => ({ uuid: d.uuid, key: d.deployment.id }))}
            tasks={tasks}
          />
        }
      />
      <form method="get" className="flex flex-col gap-3 sm:flex-row sm:items-end" aria-label="Filtrar">
        <div className="flex min-w-0 flex-col gap-1 sm:w-80">
          <Label htmlFor="cert-deployment">Despliegue</Label>
          <Input id="cert-deployment" name="deployment" defaultValue={deployment ?? ""} placeholder="bedrock/eu.anthropic.…" />
        </div>
        <div className="flex min-w-0 flex-col gap-1 sm:w-48">
          <Label htmlFor="cert-task">Tarea</Label>
          <NativeSelect id="cert-task" name="task" defaultValue={task ?? ""}>
            <option value="">Todas</option>
            {tasks.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </NativeSelect>
        </div>
        <Button type="submit" variant="outline">
          Filtrar
        </Button>
      </form>
      {battery && battery.coverage_gaps.length ? (
        <Callout tone="warning" title={`La batería v${battery.version} está incompleta`}>
          {battery.cases} casos. {battery.coverage_gaps.join(" ")}
        </Callout>
      ) : null}
      {data === null ? (
        <ErrorState title="No se pudieron leer las certificaciones" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <CertificationsView data={data} />
      )}
    </>
  );
}
