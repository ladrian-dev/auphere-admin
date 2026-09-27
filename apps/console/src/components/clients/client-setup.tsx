"use client";

import Link from "next/link";

import { Button, Section, Stepper, type StepState } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { ClientSetupDetail } from "@/lib/backend";
import type { Role } from "@/lib/permissions";

import { ClientLifecycleActions } from "./lifecycle-actions";
import { nextAction, setupSteps, whoCanResolve } from "./client-header-model";

/**
 * «Puesta en marcha»: qué le falta al cliente para atender (spec 017 R1.1;
 * aligerada por la spec 018 R6).
 *
 * Un solo botón —el del paso pendiente— y una línea que dice por qué
 * importa. En cuanto atiende, el bloque desaparece: ya no hay nada que poner
 * en marcha.
 *
 * **El crédito ya no está aquí.** Compartía fila con los cuatro pasos y eso
 * era lo que hacía la tarjeta pesada, pero la razón de fondo es otra: el
 * crédito **sobrevive** a la puesta en marcha. Sigue importando cuando los
 * cuatro pasos están hechos y este bloque ya no existe, así que su sitio es
 * el Resumen.
 */
export function ClientSetup({
  refId,
  name,
  status,
  role,
  setup,
  agentVersion,
  phone,
}: {
  refId: string;
  name: string;
  status: string;
  role: Role;
  setup: ClientSetupDetail | null;
  /** Paridad fila 7: el dato de cada paso hecho, a la vista. */
  agentVersion?: number | null;
  phone?: string | null;
}) {
  const t = useT();
  const base = `/clients/${encodeURIComponent(refId)}`;
  const steps = setupSteps(setup);
  const pending = setup?.next ?? null;
  const action = nextAction(setup, role, base);
  const doneCount = steps.filter((s) => s.done).length;

  function stepDetail(step: string): string | null {
    if (step === "agent" && agentVersion) return t("clients.setup.detail.agent", { version: agentVersion });
    if (step === "channel" && phone) return phone;
    return null;
  }

  // R6.2: cuando los cuatro pasos están hechos no hay nada que poner en
  // marcha, y el bloque entero desaparece. El crédito NO se va con él: vive
  // en el Resumen, porque le sobrevive.
  if (!pending) return null;

  return (
    <Section title={t("clients.setup.title")} description={t("clients.setup.description")} className="min-w-0">
      {/* `ordered={false}`: los cuatro pasos son independientes, y los
              ordinales con línea de unión son la gramática de una secuencia
              — un «paso 3 hecho, paso 2 no» se leería como imposible. */}
          <Stepper
            variant="line"
            ordered={false}
            ariaLabel={t("clients.setup.title")}
            current={-1}
            // Un paso hecho dice CUÁL: «Agente · versión 3», «Canal · +34…».
            // El dato iba en un tooltip, y lo que solo existe al pasar el
            // ratón no existe en una pantalla táctil ni en un lector.
            steps={steps.map((s) => ({
              key: s.step,
              label: (
                <span className="inline-flex flex-wrap items-baseline gap-x-1">
                  {t(s.label)}
                  {s.done && stepDetail(s.step) ? (
                    <span className="text-xs text-muted-foreground">· {stepDetail(s.step)}</span>
                  ) : null}
                </span>
              ),
              state: (s.done ? "done" : s.next ? "current" : "todo") as StepState,
            }))}
            stepOfLabel={() => t("clients.setup.done", { done: doneCount, total: steps.length })}
          />
          <div className="flex flex-col gap-2 pt-1">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="text-sm text-muted-foreground">{t("clients.setup.next")}</span>
              {action?.kind === "link" ? (
                <Button nativeButton={false} render={<Link href={action.href} />}>
                  {t(action.label)}
                </Button>
              ) : action?.kind === "activate" ? (
                <ClientLifecycleActions refId={refId} status={status} name={name} canDelete={false} />
              ) : (
                // Un botón que da 403 es peor que ningún botón: se dice
                // quién puede resolverlo.
                <span className="text-sm">
                  {t(pendingLabel(pending))} <span className="text-muted-foreground">{t(whoCanResolve(pending))}</span>
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{t(whyLabel(pending))}</p>
          </div>
    </Section>
  );
}

function pendingLabel(step: NonNullable<ClientSetupDetail["next"]>) {
  return `clients.setup.next.${step}` as const;
}

function whyLabel(step: NonNullable<ClientSetupDetail["next"]>) {
  return `clients.setup.why.${step}` as const;
}
