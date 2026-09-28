"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  HelpHint,
  NativeSelect,
  StatusBadge,
  Switch,
} from "@nexus/ui";

import { setCapabilityAction } from "@/app/(console)/clients/[ref]/capabilities/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { Capability, CapabilityModeChange } from "@/lib/backend/capabilities";

/**
 * Una habilidad (spec 017 R5; aligerada con el owner el 2026-09-28).
 *
 * **La tarjeta pesa poco y la ficha lo cuenta todo.** Antes cada tarjeta
 * llevaba encima hasta seis insignias, el aviso de su conector, el selector
 * de modo y el detalle técnico plegado: con treinta y siete en pantalla, eso
 * no es una lista, es un muro. Ahora la tarjeta dice **nombre, una línea y
 * el interruptor**, y lo demás vive en una ficha que se abre al pulsarla.
 *
 * Nada se ha perdido de sitio: se ha movido a donde se lee cuando hace falta
 * —antes de encenderla—, en vez de competir por la atención de golpe.
 *
 * Lo que esta tarjeta decide:
 *
 * - **El interruptor guarda al soltarlo.** Una casilla diría «marca y luego
 *   confirma», que es lo que hacía la pantalla vieja con su botón «Guardar
 *   herramientas»; aquí el clic ya guarda y la casilla mentiría.
 * - **Abrir no es encender.** El cuerpo de la tarjeta abre la ficha; el
 *   interruptor enciende. Son dos objetivos distintos y no se solapan, ni
 *   con el ratón ni con el teclado.
 * - **Quien no puede escribir no ve interruptor**, y el estado se lee igual
 *   en una insignia. Un control muerto es peor que ninguno.
 * - **Le falta su conector y se puede encender igual** (owner, 2026-09-26):
 *   encenderla es decir «la quiero». La ficha dice qué falta y enlaza a
 *   conectarlo.
 */
export function CapabilityCard({
  refId,
  cap,
  canWrite,
  onChanged,
}: {
  refId: string;
  cap: Capability;
  canWrite: boolean;
  onChanged?: () => void;
}) {
  const t = useT();
  const [enabled, setEnabled] = React.useState(cap.enabled);
  const [pending, startTransition] = React.useTransition();
  const [open, setOpen] = React.useState(false);
  const nameId = `cap-${cap.kind}-${cap.key}`;

  // El servidor manda: si vuelve otro valor, la tarjeta lo acepta en vez de
  // quedarse con lo que el usuario pulsó.
  const [seen, setSeen] = React.useState(cap.enabled);
  if (seen !== cap.enabled) {
    setSeen(cap.enabled);
    setEnabled(cap.enabled);
  }

  function save(change: { enabled?: boolean; mode?: CapabilityModeChange }) {
    startTransition(async () => {
      const res = await setCapabilityAction({ ref: refId, key: cap.key, kind: cap.kind, ...change });
      if (!res.ok) {
        if (change.enabled !== undefined) setEnabled(!change.enabled);
        toast.error(actionErrorText(res, t));
        return;
      }
      toast.success(t("cap.saved"));
      onChanged?.();
    });
  }

  return (
    <li
      className="flex min-w-0 items-start gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10 focus-within:ring-2 focus-within:ring-ring"
      aria-busy={pending}
    >
      {/* El cuerpo es el objetivo de «abrir». Un botón de verdad, para que
          el teclado lo alcance y un lector de pantalla diga qué hace. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex min-w-0 flex-1 cursor-pointer flex-col gap-1 text-left outline-none"
        aria-haspopup="dialog"
      >
        <span id={nameId} className="font-medium">
          {cap.business_name}
        </span>
        {/* Dos líneas y basta: lo que no cabe se lee en la ficha. */}
        <span className="line-clamp-2 text-sm text-pretty text-muted-foreground">{cap.description}</span>
        {/* Solo lo que cambia una decisión **antes** de abrir: que no se pueda
            encender, o que le falte algo para funcionar. El resto —recomendada,
            de otro sector, publicada o no— está dentro. */}
        {!cap.activatable ? (
          <StatusBadge tone="muted">{t("cap.unavailable.badge")}</StatusBadge>
        ) : cap.connector && cap.connector.status !== "connected" ? (
          <span className="text-xs text-warning">{t("cap.needs", { name: cap.connector.display_name })}</span>
        ) : null}
      </button>

      {!cap.activatable ? null : canWrite ? (
        <Switch
          aria-labelledby={nameId}
          checked={enabled}
          disabled={pending}
          onCheckedChange={(v) => {
            const next = Boolean(v);
            setEnabled(next);
            save({ enabled: next });
          }}
        />
      ) : (
        <StatusBadge tone={enabled ? "positive" : "muted"}>
          {enabled ? t("cap.state.on") : t("cap.state.off")}
        </StatusBadge>
      )}

      <CapabilityDialog
        refId={refId}
        cap={cap}
        canWrite={canWrite}
        open={open}
        onOpenChange={setOpen}
        pending={pending}
        onMode={(mode) => save({ mode })}
      />
    </li>
  );
}

/**
 * Todo lo que se sabe de una habilidad, antes de encenderla.
 *
 * Es lo que la tarjeta llevaba encima: las insignias de estado, qué le falta,
 * cuándo la usa el agente y el nombre interno. Aquí caben sin apretarse, y
 * sobre todo **se leen cuando se van a usar**: al decidir si se enciende.
 */
function CapabilityDialog({
  refId,
  cap,
  canWrite,
  open,
  onOpenChange,
  pending,
  onMode,
}: {
  refId: string;
  cap: Capability;
  canWrite: boolean;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  pending: boolean;
  onMode: (mode: CapabilityModeChange) => void;
}) {
  const t = useT();
  const base = `/clients/${encodeURIComponent(refId)}`;
  const modeId = `cap-mode-${cap.kind}-${cap.key}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{cap.business_name}</DialogTitle>
          <DialogDescription>{cap.description}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            {cap.recommended ? <StatusBadge tone="info">{t("cap.badge.recommended")}</StatusBadge> : null}
            {cap.enabled_in_active ? (
              <StatusBadge tone="positive">{t("cap.badge.inActive")}</StatusBadge>
            ) : cap.enabled ? (
              <StatusBadge tone="info">{t("cap.badge.notPublished")}</StatusBadge>
            ) : null}
            {cap.other_sector ? <StatusBadge tone="muted">{t("cap.badge.otherSector")}</StatusBadge> : null}
            {cap.read_only ? <StatusBadge tone="muted">{t("cap.badge.readOnly")}</StatusBadge> : null}
            {cap.destructive ? <StatusBadge tone="danger">{t("cap.badge.destructive")}</StatusBadge> : null}
            {!cap.activatable ? <StatusBadge tone="muted">{t("cap.unavailable.badge")}</StatusBadge> : null}
          </div>

          {!cap.activatable ? (
            // Paridad fila 57. No es «avisar y dejar encender» como con un
            // conector que falta: allí encenderla es una decisión que se
            // cumple al conectar, aquí no hay nada que escribir hasta que
            // Auphere la suba. Se dice de quién depende.
            <p className="text-sm text-muted-foreground">{t("cap.unavailable")}</p>
          ) : null}

          {cap.connector && cap.connector.status !== "connected" ? (
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-warning">
              {t("cap.needs", { name: cap.connector.display_name })}{" "}
              <Link href={`${base}/integrations`} className="underline underline-offset-4">
                {t("cap.needs.connect")}
              </Link>
              <HelpHint label={`${t("cap.needs.connect")}: ${cap.connector.display_name}`}>
                {t("cap.needs.help", { name: cap.connector.display_name })}
              </HelpHint>
            </p>
          ) : null}

          {cap.mode && canWrite ? (
            <div className="flex flex-col gap-2">
              <label htmlFor={modeId} className="text-sm font-medium">
                {t("cap.mode.label")}
              </label>
              <span className="flex items-center gap-2">
                <NativeSelect
                  id={modeId}
                  size="sm"
                  defaultValue={cap.mode.override ?? "__default"}
                  disabled={pending}
                  wrapperClassName="w-52"
                  onChange={(e) => {
                    const v = e.target.value;
                    // «Por defecto» pide **borrar** lo fijado, no guardar el
                    // valor por defecto: guardarlo dejaba la ayuda «lo has
                    // fijado tú» puesta para siempre.
                    onMode((v === "__default" ? "default" : v) as CapabilityModeChange);
                  }}
                >
                  <option value="__default">
                    {t("cap.mode.default", { mode: t(`cap.mode.${cap.mode.default}`) })}
                  </option>
                  {cap.mode.options.map((m) => (
                    <option key={m} value={m}>
                      {t(`cap.mode.${m}`)}
                    </option>
                  ))}
                </NativeSelect>
                {cap.mode.override ? <HelpHint label={t("cap.mode.label")}>{t("cap.mode.overridden")}</HelpHint> : null}
              </span>
            </div>
          ) : null}

          {/* El nombre interno existe pero no compite con el del negocio (R5.6). */}
          <details className="min-w-0 text-xs text-muted-foreground">
            <summary className="cursor-pointer">{t("cap.technical")}</summary>
            <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
              <span>
                <dt className="inline">{t("cap.technical.name")}: </dt>
                <dd className="inline font-mono">{cap.technical.name}</dd>
              </span>
              <span>
                <dt className="inline">{t("cap.technical.kind")}: </dt>
                <dd className="inline">{t(`cap.technical.kind.${cap.technical.kind}`)}</dd>
              </span>
              {cap.technical.version ? (
                <span>
                  <dt className="inline">{t("cap.technical.version")}: </dt>
                  <dd className="inline">{cap.technical.version}</dd>
                </span>
              ) : null}
              {cap.technical.tags.length ? (
                <span>
                  <dt className="inline">{t("cap.technical.tags")}: </dt>
                  <dd className="inline font-mono">{cap.technical.tags.join(" ")}</dd>
                </span>
              ) : null}
            </dl>
          </details>
        </div>
      </DialogContent>
    </Dialog>
  );
}
