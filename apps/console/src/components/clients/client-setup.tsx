"use client";

import Link from "next/link";

import { Button, HelpHint, Meter, type MeterTone, Section, Stepper, type StepState } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { ClientQuota, ClientSetupDetail } from "@/lib/backend";
import { can, type Role } from "@/lib/permissions";

import { ClientLifecycleActions } from "./lifecycle-actions";
import { nextAction, setupSteps, whoCanResolve } from "./client-header-model";

/**
 * Las dos tarjetas de la cabecera de la ficha (spec 017, R1.1–R1.3): qué
 * falta para que el cliente atienda, y cuánto crédito le queda.
 *
 * Mientras falta algo, «Puesta en marcha» con UN solo botón — el del paso
 * pendiente — y una línea que dice por qué importa. En cuanto atiende, el
 * bloque desaparece: ya no hay nada que poner en marcha.
 */
export function ClientSetup({
  refId,
  name,
  status,
  role,
  setup,
  quota,
}: {
  refId: string;
  name: string;
  status: string;
  role: Role;
  setup: ClientSetupDetail | null;
  quota: ClientQuota | null;
}) {
  const t = useT();
  const base = `/clients/${encodeURIComponent(refId)}`;
  const steps = setupSteps(setup);
  const pending = setup?.next ?? null;
  const action = nextAction(setup, role, base);
  const doneCount = steps.filter((s) => s.done).length;

  return (
    <div className="grid gap-(--space-block) lg:grid-cols-[2fr_1fr]">
      {pending ? (
        <Section title={t("clients.setup.title")} description={t("clients.setup.description")} className="min-w-0">
          {/* `ordered={false}`: los cuatro pasos son independientes, y los
              ordinales con línea de unión son la gramática de una secuencia
              — un «paso 3 hecho, paso 2 no» se leería como imposible. */}
          <Stepper
            variant="line"
            ordered={false}
            ariaLabel={t("clients.setup.title")}
            current={-1}
            steps={steps.map((s) => ({
              key: s.step,
              label: t(s.label),
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
      ) : null}

      <Section
        title={
          <span className="inline-flex items-center gap-1">
            {t("clients.quota.title")} <HelpHint label={t("clients.quota.title")}>{t("clients.quota.help")}</HelpHint>
          </span>
        }
        actions={
          can(role, "usage:write") ? (
            <Button size="xs" variant="ghost" nativeButton={false} render={<Link href="/usage" />}>
              {t("clients.quota.manage")}
            </Button>
          ) : undefined
        }
        className="min-w-0"
      >
        {quota ? (
          <Meter
            label={t("clients.quota.label")}
            labelHidden
            value={quota.remaining}
            max={quota.cap}
            tone={creditTone(quota)}
            valueLabel={t("clients.quota.value", { remaining: quota.remaining, cap: quota.cap })}
            hint={t("clients.quota.spent", { spent: quota.cap - quota.remaining })}
          />
        ) : (
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("clients.quota.none")}</p>
        )}
      </Section>
    </div>
  );
}

/** La barra mide lo que QUEDA, así que su tono también: verde mientras
 *  sobra, aviso por debajo del 20 %, rojo cuando se agotó. */
function creditTone({ cap, remaining }: ClientQuota): MeterTone {
  if (remaining <= 0) return "danger";
  if (cap > 0 && remaining / cap <= 0.2) return "warning";
  return "positive";
}

function pendingLabel(step: NonNullable<ClientSetupDetail["next"]>) {
  return `clients.setup.next.${step}` as const;
}

function whyLabel(step: NonNullable<ClientSetupDetail["next"]>) {
  return `clients.setup.why.${step}` as const;
}
