"use client";

import { Section, StepTrack, formatNumber } from "@nexus/ui";

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
  // Se cuentan **pasos**, no partes: hay tantas barras como pasos, y un
  // contador que cuente otra cosa no cuadra con lo que se ve. Las partes
  // siguen existiendo, pero solo para rellenar la barra a medias.
  const hechos = steps.filter((s) => s.done >= s.of).length;
  const total = steps.length;

  return (
    <Section
      title={t("clients.setup.title")}
      description={t("clients.setup.description")}
      // El recuento a la derecha del título: equilibra la cabecera y es lo
      // primero que se quiere saber al volver a un cliente a medias.
      actions={
        <span className="text-sm text-muted-foreground tabular-nums">
          {t("clients.setup.done", { done: hechos, total })}
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
          href: s.step === pending && action?.kind === "link" ? action.href : undefined,
        }))}
        ariaLabel={t("clients.setup.title")}
        summary={t("clients.setup.done", { done: hechos, total })}
      />

      {/* Ni botón ni explicación al pie: la flecha del paso pendiente ya
          dice dónde se resuelve, y la tarjeta se lee de un vistazo en vez
          de pedir que se lea entera (owner, 2026-09-28). Lo único que
          sobrevive es quién puede resolverlo cuando tú no puedes: sin esa
          frase, a ese rol la tarjeta no le dice nada. */}
      {action?.kind === "link" ? null : action?.kind === "activate" ? (
        <div className="pt-1">
          <ClientLifecycleActions refId={refId} status={status} name={name} canDelete={false} />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t(whoCanResolve(pending))}</p>
      )}
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

