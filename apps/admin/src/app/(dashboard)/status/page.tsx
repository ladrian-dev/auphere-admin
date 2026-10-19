import { DescriptionList, ErrorState, PageHeader, Section, StatusBadge } from "@nexus/ui";

import { backend } from "@/lib/backend";

export const metadata = { title: "Estado" };
export const dynamic = "force-dynamic";

const ENV_LABEL: Record<string, string> = { production: "Producción", staging: "Staging", dev: "Desarrollo local" };
const CHECK_LABEL: Record<string, string> = { postgres: "Base de datos", redis: "Redis" };

/** Spec 031 (R6): is the API up, where is it, and what is deployed. */
export default async function StatusPage() {
  const instance = await backend.getInstance().catch(() => null);
  return (
    <>
      <PageHeader title="Estado" description="Qué entorno es este, qué versión corre y si sus dependencias responden." />
      {!instance ? (
        <ErrorState title="La API no responde" description="No se pudo leer el estado de la instancia. Si persiste, revisa el despliegue de la API." />
      ) : (
        <>
          <Section title="Despliegue">
            <DescriptionList
              items={[
                { key: "env", term: "Entorno", detail: ENV_LABEL[instance.environment] ?? instance.environment },
                { key: "schema", term: "Versión del esquema", detail: instance.schema_revision ?? "No se pudo leer", mono: true },
                { key: "commit", term: "Commit de la API", detail: instance.commit === "unknown" ? "Sin dato (build local)" : instance.commit.slice(0, 12), mono: true },
              ]}
            />
          </Section>
          <Section title="Dependencias">
            <ul className="flex flex-col divide-y divide-border">
              {Object.entries(instance.checks).map(([name, value]) => (
                <li key={name} className="flex items-center justify-between gap-4 py-3">
                  <span className="text-sm">{CHECK_LABEL[name] ?? name}</span>
                  {value === "ok" ? (
                    <StatusBadge tone="positive">Responde</StatusBadge>
                  ) : (
                    <StatusBadge tone="danger">{value.replace("error: ", "Error · ")}</StatusBadge>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        </>
      )}
    </>
  );
}
