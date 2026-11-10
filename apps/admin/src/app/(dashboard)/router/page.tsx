import { ErrorState, PageHeader, Section } from "@nexus/ui";
import { modelsBackend } from "@/lib/backend-models";

import { ProfileEditor } from "./profile-editor";
import { RoutePreview } from "./route-preview";
import { RouterTabs } from "./router-tabs";

export const metadata = { title: "Router" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T150, historia 30, 40.13, 54.2): the router's policy without
 * touching the database — each change a new version with who and why, from
 * the next turn — and a preview of what it would choose for an agent.
 */
export default async function RouterPage() {
  const [taxonomy, profiles, deployments] = await Promise.all([
    modelsBackend.taxonomy().catch(() => null),
    modelsBackend.profiles().catch(() => null),
    modelsBackend.listDeployments().catch(() => null),
  ]);
  return (
    <>
      <PageHeader
        title="Router"
        description="La política de cada perfil, tarea por tarea. Un cambio es una versión nueva con su motivo, y se aplica desde el siguiente turno."
      />
      <RouterTabs current="/router" />
      {profiles === null || taxonomy === null ? (
        <ErrorState title="No se pudo leer la política" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <>
          <Section
            title="Perfiles"
            description={`Taxonomía v${taxonomy.version}: ${taxonomy.tasks.length} tareas. Los techos del requisito 40.10 se pueden bajar, nunca subir.`}
          >
            <ProfileEditor
              profiles={profiles.items}
              ceilings={profiles.ceilings}
              deployments={(deployments?.items ?? []).map((d) => d.deployment.id).sort()}
            />
          </Section>
          <Section
            title="Vista previa"
            description="Qué despliegue elegiría para una tarea de un agente, con los descartados y su motivo. No llama a ningún modelo."
          >
            <RoutePreview tasks={taxonomy.tasks} profiles={profiles.items.map((p) => p.profile)} />
          </Section>
        </>
      )}
    </>
  );
}
