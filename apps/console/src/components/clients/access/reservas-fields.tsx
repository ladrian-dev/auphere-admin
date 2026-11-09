"use client";

import * as React from "react";

import { Label, NativeSelect, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import { CAPACITY_KINDS, type CapacityKind, type ClientAccess, type ReservasMode } from "@/lib/backend/client-access";

/**
 * El modo de Reservas y, en Aforo, el tipo de negocio (spec 056, requisito 3.3).
 * Lo comparten la pestaña Acceso (`client-console-card.tsx`), «Nuevo agente» y la
 * confirmación de «Agenda (Reservas)» en Conectores (spec 057, requisitos 1.3 y
 * 2.3): un solo nombre y una sola forma de elegir lo mismo.
 *
 * En Acceso, la primera vez se elige y, después, cambiarlo con reservas futuras
 * pregunta antes (lo hace quien lo monta). `stored` es lo guardado: con él, un
 * tipo distinto dice que renombra. Los `id` salen de `useId`: dos en la misma
 * página no chocan.
 */
export function ReservasFields({
  mode,
  kind,
  stored = null,
  disabled,
  onMode,
  onKind,
  className,
}: {
  mode: ReservasMode | null;
  kind: CapacityKind | null;
  stored?: Pick<NonNullable<ClientAccess["reservas"]>, "mode" | "capacity_kind"> | null;
  disabled: boolean;
  onMode: (m: ReservasMode) => void;
  onKind: (k: CapacityKind | null) => void;
  className?: string;
}) {
  const t = useT();
  const base = React.useId();
  const modeErrorId = `${base}-mode-error`;
  const kindId = `${base}-kind`;
  const kindErrorId = `${base}-kind-error`;
  const kindNoteId = `${base}-kind-note`;
  const modeMissing = mode === null;
  const kindMissing = mode === "capacity" && kind === null;
  const renames = stored?.mode === "capacity" && kind !== null && kind !== stored.capacity_kind;
  return (
    <div className={cn("grid min-w-0 gap-4", className)} data-slot="reservas-fields">
      <fieldset className="grid min-w-0 gap-2" disabled={disabled} aria-describedby={modeMissing ? modeErrorId : undefined}>
        <legend className="mb-1 text-sm font-medium">{t("clientAccess.reservas.mode")}</legend>
        {(["services", "capacity"] as const).map((m) => (
          <label key={m} className="flex min-h-6 min-w-0 items-start gap-3 text-sm">
            <input
              type="radio"
              name={`${base}-mode`}
              value={m}
              checked={mode === m}
              onChange={() => onMode(m)}
              className="mt-1 size-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            />
            <span className="min-w-0 text-pretty">
              <span className="font-medium">{t(`clientAccess.reservas.mode.${m}` as MessageKey)}</span>{" "}
              <span className="text-muted-foreground">{t(`clientAccess.reservas.mode.${m}.hint` as MessageKey)}</span>
            </span>
          </label>
        ))}
        {modeMissing ? (
          <p id={modeErrorId} className="text-xs text-destructive">
            {t("clientAccess.error.reservas_mode_required")}
          </p>
        ) : null}
      </fieldset>
      {mode === "capacity" ? (
        <div className="grid min-w-0 gap-2">
          <Label htmlFor={kindId} className="text-sm font-medium">
            {t("clientAccess.reservas.kind")}
          </Label>
          <NativeSelect
            id={kindId}
            value={kind ?? ""}
            onChange={(e) => onKind(e.target.value === "" ? null : (e.target.value as CapacityKind))}
            disabled={disabled}
            required
            aria-invalid={kindMissing || undefined}
            aria-describedby={kindMissing ? kindErrorId : renames ? kindNoteId : undefined}
            wrapperClassName="w-full sm:max-w-xs"
          >
            <option value="" disabled>
              {t("clientAccess.reservas.kind.pick")}
            </option>
            {CAPACITY_KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`clientAccess.reservas.kind.${k}` as MessageKey)}
              </option>
            ))}
          </NativeSelect>
          {kindMissing ? (
            <p id={kindErrorId} className="text-xs text-destructive">
              {t("clientAccess.error.reservas_kind_required")}
            </p>
          ) : null}
          {renames ? (
            <p id={kindNoteId} className="text-xs text-pretty text-muted-foreground">
              {t("clientAccess.reservas.kind.renames")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
