"use client";

import Link from "next/link";

import { Button, Section, StepTrack, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { ClientQuota, ClientSetupDetail } from "@/lib/backend";
import type { Role } from "@/lib/permissions";

import { ClientLifecycleActions } from "./lifecycle-actions";
import { nextAction, whoCanResolve } from "./client-header-model";

/**
 * «Puesta en marcha»: qué le falta al cliente para atender (spec 017 R1.1;
 * aligerada por la spec 018 R6 y rehecha el 2026-09-28 con el owner).
 *
 * **Lo que cambió y por qué.** Eran cuatro palomas verdes —hecho o no
 * hecho— alineadas a la izquierda de una tarjeta ancha: mucho blanco a la
 * derecha, todo el peso a un lado, y una mentira por omisión. «Agente» son
 * dos cosas (escribirlo y publicarlo) y «Activación» una sola, y con una
 * paloma cada uno el partner no podía saber cuál le iba a costar.
 *
 * Ahora cada paso lleva su barra con **cuánto lleva hecho**, y su ancho sale
 * del número de partes que tiene. Eso contesta «¿cuál es el que cuesta?» sin
 * afirmar cuánto tarda cada uno, que es un dato que no tenemos.
 *
 * **El crédito no está aquí.** Compartía fila con los pasos y eso hacía la
 * tarjeta pesada, pero la razón de fondo es que le **sobrevive**: sigue
 * importando cuando los cuatro pasos están hechos y este bloque ya no
 * existe, así que vive en el Resumen.
 */
export function ClientSetup({
  refId,
  name,
  status,
  role,
  setup,
  quota,
  agentVersion,
  phone,
  hasAgentVersion = false,
}: {
  refId: string;
  name: string;
  status: string;
  role: Role;
  setup: ClientSetupDetail | null;
  quota: ClientQuota | null;
  /** Paridad fila 7: el dato de cada paso hecho, a la vista. */
  agentVersion?: number | null;
  phone?: string | null;
  /** Hay alguna versión escrita, aunque no esté publicada. */
  hasAgentVersion?: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const base = `/clients/${encodeURIComponent(refId)}`;
  const pending = setup?.next ?? null;
  const action = nextAction(setup, role, base);

  // R6.2: cuando los cuatro pasos están hechos no hay nada que poner en
  // marcha, y el bloque entero desaparece.
  if (!pending) return null;

  const steps = subSteps({ setup, quota, agentVersion, phone, hasAgentVersion, status, locale });
  const hechas = steps.reduce((n, s) => n + s.done, 0);
  const total = steps.reduce((n, s) => n + s.of, 0);

  return (
    <Section
      title={t("clients.setup.title")}
      description={t("clients.setup.description")}
      // El recuento a la derecha del título: equilibra la cabecera y es lo
      // primero que se quiere saber al volver a un cliente a medias.
      actions={
        <span className="text-sm text-muted-foreground tabular-nums">
          {t("clients.setup.partsDone", { done: hechas, total })}
        </span>
      }
      className="min-w-0"
    >
      <StepTrack
        steps={steps.map((s) => ({
          key: s.step,
          label: t(s.label),
          done: s.done,
          of: s.of,
          detail: s.detail,
          current: s.step === pending,
        }))}
        ariaLabel={t("clients.setup.title")}
        summary={t("clients.setup.partsDone", { done: hechas, total })}
      />

      {/* La acción y su porqué en una fila: la razón a la derecha del botón
          en vez de debajo, que es lo que dejaba la mitad derecha vacía. */}
      <div className="flex flex-wrap items-center gap-x-(--space-block) gap-y-2 pt-1">
        {action?.kind === "link" ? (
          <Button nativeButton={false} render={<Link href={action.href} />}>
            {t(action.label)}
          </Button>
        ) : action?.kind === "activate" ? (
          <ClientLifecycleActions refId={refId} status={status} name={name} canDelete={false} />
        ) : (
          // Un botón que da 403 es peor que ningún botón: se dice quién
          // puede resolverlo.
          <span className="text-sm">
            {t(pendingLabel(pending))} <span className="text-muted-foreground">{t(whoCanResolve(pending))}</span>
          </span>
        )}
        <p className="min-w-0 flex-1 text-sm text-pretty text-muted-foreground">{t(whyLabel(pending))}</p>
      </div>
    </Section>
  );
}

type SubStep = {
  step: NonNullable<ClientSetupDetail["next"]>;
  label: Parameters<ReturnType<typeof useT>>[0];
  done: number;
  of: number;
  detail?: string | null;
};

/**
 * Las partes de cada paso, **derivadas de lo que la ficha ya sabe**. Ninguna
 * necesita una lectura nueva, y ninguna afirma un dato que no tenemos: el
 * ancho lo da el número de partes, no una estimación de esfuerzo.
 */
function subSteps({
  setup,
  quota,
  agentVersion,
  phone,
  hasAgentVersion,
  status,
  locale,
}: {
  setup: ClientSetupDetail | null;
  quota: ClientQuota | null;
  agentVersion?: number | null;
  phone?: string | null;
  hasAgentVersion: boolean;
  status: string;
  locale: "es" | "en";
}): SubStep[] {
  const publicado = Boolean(agentVersion);
  const pasos: SubStep[] = [
    {
      // Escribirlo y publicarlo son dos cosas, y la segunda es la que el
      // agente necesita para saber qué decir.
      step: "agent",
      label: "clients.setup.agent",
      done: (hasAgentVersion || publicado ? 1 : 0) + (publicado ? 1 : 0),
      of: 2,
      detail: publicado ? `v${agentVersion}` : hasAgentVersion ? null : null,
    },
    {
      step: "channel",
      label: "clients.setup.channel",
      done: setup?.channel ? 1 : 0,
      of: 1,
      detail: phone ?? null,
    },
    {
      // Tener tope y tener saldo no es lo mismo: un cliente con el cupo
      // agotado tiene el paso hecho y al agente callado.
      step: "quota",
      label: "clients.setup.quota",
      done: (quota ? 1 : 0) + (quota && quota.remaining > 0 ? 1 : 0),
      of: 2,
      // Toda cifra pasa por Intl: «50000» en crudo no es un número, es
      // una cadena que casualmente tiene dígitos.
      detail: quota ? formatNumber(quota.remaining, locale) : null,
    },
  ];
  // «Activación» solo es un paso cuando de verdad falta. Un cliente se crea
  // ya activo, así que este segmento nacía verde y no volvía a moverse: un
  // tramo permanentemente lleno enseña al ojo a ignorar la barra entera. Si
  // alguien pausa o archiva el cliente, entonces sí es lo que le falta, y
  // entonces aparece.
  if (status !== "active") {
    pasos.push({ step: "activation", label: "clients.setup.activation", done: 0, of: 1 });
  }
  return pasos;
}

function pendingLabel(step: NonNullable<ClientSetupDetail["next"]>) {
  return `clients.setup.next.${step}` as const;
}

function whyLabel(step: NonNullable<ClientSetupDetail["next"]>) {
  return `clients.setup.why.${step}` as const;
}
