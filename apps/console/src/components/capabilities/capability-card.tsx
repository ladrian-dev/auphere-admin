"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { HelpHint, NativeSelect, StatusBadge, Switch } from "@nexus/ui";

import { setCapabilityAction } from "@/app/(console)/clients/[ref]/capabilities/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { Capability, CapabilityModeChange } from "@/lib/backend/capabilities";

/**
 * Una capacidad (spec 017, R5). Por dentro puede ser una herramienta o una
 * habilidad; aquí es lo mismo, porque para el partner lo es.
 *
 * Lo que esta tarjeta decide:
 *
 * - **El interruptor guarda al soltarlo.** Una casilla diría «marca y luego
 *   confirma», que es lo que hacía la pantalla vieja con su botón «Guardar
 *   herramientas»; aquí el clic ya guarda y la casilla mentiría.
 * - **Quien no puede escribir no ve interruptor**, y el estado se lee igual
 *   en una insignia. Un control muerto es peor que ninguno.
 * - **Le falta su integración y se puede encender igual** (owner,
 *   2026-09-26): encenderla es decir «la quiero». La tarjeta dice qué falta
 *   y enlaza a conectarlo.
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
  const nameId = `cap-${cap.kind}-${cap.key}`;
  const base = `/clients/${encodeURIComponent(refId)}`;

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
    <li className="flex min-w-0 flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-busy={pending}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span id={nameId} className="font-medium">
              {cap.business_name}
            </span>
            {cap.recommended ? <StatusBadge tone="info">{t("cap.badge.recommended")}</StatusBadge> : null}
            {cap.enabled_in_active ? (
              <StatusBadge tone="positive">{t("cap.badge.inActive")}</StatusBadge>
            ) : enabled ? (
              <StatusBadge tone="info">{t("cap.badge.notPublished")}</StatusBadge>
            ) : null}
            {cap.other_sector ? <StatusBadge tone="muted">{t("cap.badge.otherSector")}</StatusBadge> : null}
            {cap.read_only ? <StatusBadge tone="muted">{t("cap.badge.readOnly")}</StatusBadge> : null}
            {cap.destructive ? <StatusBadge tone="danger">{t("cap.badge.destructive")}</StatusBadge> : null}
          </div>
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">{cap.description}</p>
        </div>
        {!cap.activatable ? (
          // Paridad fila 57. No es «avisar y dejar encender» como con una
          // integración que falta: allí encenderla es una decisión que se
          // cumple al conectar, aquí no hay nada que escribir hasta que
          // Auphere la suba. Un conmutador que siempre falla es peor que
          // ninguno, así que se dice de quién depende y se quita.
          <StatusBadge tone="muted">{t("cap.unavailable.badge")}</StatusBadge>
        ) : canWrite ? (
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
      </div>

      {!cap.activatable ? (
        <p className="text-xs text-muted-foreground">{t("cap.unavailable")}</p>
      ) : null}

      {cap.connector && cap.connector.status !== "connected" ? (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-warning">
          {t("cap.needs", { name: cap.connector.display_name })}{" "}
          <Link href={`${base}/integrations`} className="underline underline-offset-4">
            {t("cap.needs.connect")}
          </Link>
          <HelpHint label={`${t("cap.needs.connect")}: ${cap.connector.display_name}`}>
            {t("cap.needs.help", { name: cap.connector.display_name })}
          </HelpHint>
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        {cap.mode && canWrite ? (
          <span className="flex items-center gap-2">
            <label htmlFor={`${nameId}-mode`} className="text-xs text-muted-foreground">
              {t("cap.mode.label")}
            </label>
            <NativeSelect
              id={`${nameId}-mode`}
              size="sm"
              defaultValue={cap.mode.override ?? "__default"}
              disabled={pending}
              wrapperClassName="w-52"
              onChange={(e) => {
                const v = e.target.value;
                // «Por defecto» pide **borrar** lo fijado, no guardar el
                // valor por defecto: guardarlo dejaba la ayuda «lo has
                // fijado tú» puesta para siempre.
                save({ mode: (v === "__default" ? "default" : v) as CapabilityModeChange });
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
        ) : (
          <span />
        )}
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
    </li>
  );
}
