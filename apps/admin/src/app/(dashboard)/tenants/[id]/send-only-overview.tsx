import { Check, CircleDashed, CircleHelp, Lock } from "lucide-react";
import Link from "next/link";

import { Callout, DescriptionList, Section } from "@nexus/ui";

import { ReadError } from "@/components/states/read-error";
import { backend, type Tenant } from "@/lib/backend";
import { fullDateTime } from "@/lib/format";

import { sendReadinessChecks, type SendStep } from "./readiness";

const STEP_ICON = {
  done: <Check className="size-4 text-status-positive-text" aria-hidden="true" />,
  todo: <CircleDashed className="size-4 text-muted-foreground" aria-hidden="true" />,
  unknown: <CircleHelp className="size-4 text-status-warning-text" aria-hidden="true" />,
} as const;

const STEP_STATE = { done: "Hecho", todo: "Pendiente", unknown: "No se pudo comprobar" } as const;

/**
 * Spec 077 (1.4): the Resumen of a send-only client. Its «Puesta en marcha»
 * is computed by the API (`GET send-readiness`), one row per step with its
 * real state and its action; a membership step only when it has one. A
 * failed read is an error, never «0 de 4».
 */
export async function SendOnlyOverview({ tenant, partnerName }: { tenant: Tenant; partnerName: string | null }) {
  const base = `/tenants/${tenant.id}`;
  const [readiness, membership] = await Promise.all([
    backend.getSendReadiness(tenant.id).catch(() => null),
    backend.getMembership(tenant.id).catch(() => null),
  ]);
  const steps = readiness ? sendReadinessChecks({ base, readiness, membership }) : null;
  const done = steps?.filter((s) => s.state === "done").length ?? 0;

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <div className="flex min-w-0 flex-col gap-6 xl:col-span-2">
        {steps === null ? (
          <ReadError
            title="No se pudo leer la puesta en marcha"
            description="La API no respondió. Vuelve a intentarlo en unos segundos."
          />
        ) : (
          <Section
            title="Puesta en marcha"
            description={`${done} de ${steps.length} listos.`}
            padded={false}
          >
            <ol className="divide-y divide-border">
              {steps.map((s) => (
                <StepRow key={s.key} step={s} />
              ))}
            </ol>
            {done < steps.length ? (
              <p className="flex items-center gap-2 border-t border-border bg-muted/50 px-6 py-3 text-sm text-pretty text-muted-foreground">
                <Lock className="size-4 shrink-0" aria-hidden="true" />
                Hasta completarlos, la API no envía nada.
              </p>
            ) : null}
          </Section>
        )}
        {steps !== null && done === steps.length ? (
          <Callout tone="positive" title="Listo para enviar">
            Su sistema ya puede llamar a la API con su clave.
          </Callout>
        ) : null}
      </div>

      <aside className="flex min-w-0 flex-col gap-6">
        <Section title="Datos del cliente" description="Se editan desde Acciones.">
          <DescriptionList
            layout="inline"
            items={[
              { key: "slug", term: "Identificador", detail: tenant.slug, mono: true, truncate: true },
              {
                key: "partner",
                term: "Partner",
                detail: tenant.partner_id ? (
                  <Link href={`/partners/${tenant.partner_id}`} className="underline-offset-4 hover:underline">
                    {partnerName ?? "Ver partner"}
                  </Link>
                ) : (
                  "Auphere directo"
                ),
              },
              { key: "kind", term: "Tipo", detail: "Solo envío por API" },
              { key: "email", term: "Correo", detail: tenant.owner_email ?? "—", truncate: true },
              { key: "tz", term: "Zona horaria", detail: tenant.timezone },
              { key: "created", term: "Alta", detail: fullDateTime(tenant.created_at) },
            ]}
          />
        </Section>
      </aside>
    </div>
  );
}

function StepRow({ step }: { step: SendStep }) {
  return (
    <li className="flex flex-wrap items-start gap-3 px-6 py-3">
      <span className="mt-1 shrink-0">{STEP_ICON[step.state]}</span>
      <div className="flex min-w-0 flex-1 basis-60 flex-col gap-1">
        <span className="text-sm font-medium">
          {step.label}
          <span className="sr-only"> · {STEP_STATE[step.state]}</span>
        </span>
        <span className="text-sm text-pretty text-muted-foreground">{step.detail}</span>
      </div>
      {step.href && step.action ? (
        <Link
          href={step.href}
          className="inline-flex min-h-6 shrink-0 items-center text-sm font-medium text-primary-deep underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {step.action}
        </Link>
      ) : null}
    </li>
  );
}
