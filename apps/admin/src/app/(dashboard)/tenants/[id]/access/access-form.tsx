"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, Callout, Checkbox, ConfirmDialog, Label, NativeSelect } from "@nexus/ui";
import type {
  CapacityKind,
  ClientAccessIn,
  ClientAccessOut,
  ClientModule,
  ClientReservasOut,
  ReservasMode,
} from "@/lib/backend";

import { setAccessAction } from "./actions";
import {
  AGENT_PENDING_PROMOTION,
  CAPACITY_KIND_ORDER,
  CAPACITY_KINDS,
  INELIGIBLE,
  MODULE_LABELS,
  RESERVAS_MODES,
  kindPreview,
  liveReservationsText,
} from "./messages";

const ORDER: ClientModule[] = ["panel", "inbox", "reservas", "usage"];

/**
 * Spec 030 (R1.1–R1.3): switch the client console on, and choose its modules.
 * Same shape as the runtime capabilities card: rows with a checkbox and one
 * «Guardar» that only sends what changed.
 *
 * Spec 043 (R1.2, R1.4, R1.5, R9.1): «Reservas» carries its mode (and, in
 * Aforo, the kind of business). A mode change with live reservations asks
 * first: the API cancels them and tells each client only when the operator
 * says so. The agent's prepared version is linked, never promoted from here.
 */
export function AccessForm({ tenantId, access }: { tenantId: string; access: ClientAccessOut }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  // The API may still answer without the field while 043 rolls out.
  const stored: ClientReservasOut | null = access.reservas ?? null;
  const [enabled, setEnabled] = useState(access.enabled);
  const [modules, setModules] = useState<Set<ClientModule>>(new Set(access.modules));
  const [mode, setMode] = useState<ReservasMode | null>(stored?.mode ?? null);
  const [kind, setKind] = useState<CapacityKind | null>(stored?.capacity_kind ?? null);
  // `count` null = the API did not say how many.
  const [live, setLive] = useState<{ open: boolean; count: number | null }>({ open: false, count: null });
  const [liveError, setLiveError] = useState<string | null>(null);

  if (!access.eligible) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        {access.ineligible_reason ? INELIGIBLE[access.ineligible_reason] : null}
      </p>
    );
  }

  const ordered = ORDER.filter((m) => modules.has(m));
  const withReservas = modules.has("reservas");
  const chosenKind = mode === "capacity" ? kind : null;
  // The settings go only when Reservas is switched on, or its mode or kind change.
  const reservasDirty =
    withReservas &&
    (!access.modules.includes("reservas") ||
      mode !== (stored?.mode ?? null) ||
      chosenKind !== (stored?.capacity_kind ?? null));
  const modeChanges = withReservas && stored !== null && mode !== null && mode !== stored.mode;
  const missingMode = withReservas && mode === null;
  const missingKind = withReservas && mode === "capacity" && kind === null;
  const dirty = enabled !== access.enabled || ordered.join(",") !== access.modules.join(",") || reservasDirty;
  const missingModules = enabled && ordered.length === 0;
  const inboxLocked = !access.whatsapp_connected && !access.modules.includes("inbox");
  const pendingAgents = stored?.agents_pending_promotion ?? [];

  function toggle(m: ClientModule, on: boolean) {
    setModules((prev) => {
      const next = new Set(prev);
      if (on) next.add(m);
      else next.delete(m);
      return next;
    });
  }

  function body(onLive?: "cancel_and_notify"): ClientAccessIn {
    const out: ClientAccessIn = { enabled, modules: ordered };
    if (reservasDirty && mode !== null) {
      out.reservas = {
        mode,
        ...(chosenKind !== null ? { capacity_kind: chosenKind } : {}),
        ...(onLive ? { on_live: onLive } : {}),
      };
    }
    return out;
  }

  async function send(onLive?: "cancel_and_notify") {
    const res = await setAccessAction(tenantId, body(onLive));
    if (!res.ok) {
      // Someone booked since the page loaded: the same choice, with the API's count.
      if (res.code === "live_reservations") {
        setLiveError(null);
        setLive({ open: true, count: res.count ?? null });
        return;
      }
      if (onLive) {
        setLiveError(res.error);
        return;
      }
      toast.error("No se pudo guardar el acceso", { description: res.error });
      return;
    }
    setLive((prev) => ({ ...prev, open: false }));
    setLiveError(null);
    toast.success(
      !res.data.enabled
        ? "Acceso apagado: se cerraron las sesiones de sus personas"
        : onLive
          ? "Modo cambiado. Se cancelaron las reservas futuras y se avisa a cada cliente por WhatsApp"
          : "Acceso guardado",
    );
    router.refresh();
  }

  function onSave() {
    if (modeChanges && stored.live_future > 0) {
      setLiveError(null);
      setLive({ open: true, count: stored.live_future });
      return;
    }
    startTransition(() => send());
  }

  /** «No cambiar»: the stored mode comes back, the rest of the form stays. */
  function keepMode() {
    setLive((prev) => ({ ...prev, open: false }));
    setLiveError(null);
    setMode(stored?.mode ?? null);
    setKind(stored?.capacity_kind ?? null);
  }

  return (
    <div className="grid gap-4">
      <Row
        id="access-enabled"
        label="Consola lite encendida"
        description="Las personas de este cliente entran con su correo y ven solo los módulos de abajo."
        checked={enabled}
        onChange={setEnabled}
      />
      <fieldset className="grid gap-3 border-l border-border pl-4" aria-label="Módulos">
        {ORDER.map((m) => (
          <div key={m} className="grid gap-3">
            <Row
              id={`module-${m}`}
              label={MODULE_LABELS[m].label}
              description={
                m === "inbox" && inboxLocked
                  ? "La Bandeja de entrada necesita un WhatsApp conectado."
                  : MODULE_LABELS[m].description
              }
              checked={modules.has(m)}
              onChange={(on) => toggle(m, on)}
              disabled={m === "inbox" && inboxLocked}
            />
            {m === "reservas" && withReservas ? (
              <ReservasFields
                mode={mode}
                kind={kind}
                stored={stored}
                disabled={pending}
                onMode={setMode}
                onKind={setKind}
              />
            ) : null}
          </div>
        ))}
      </fieldset>
      {missingModules ? (
        <p className="text-sm text-destructive" role="alert">
          Elige al menos un módulo para encender el acceso.
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button
          type="button"
          onClick={onSave}
          disabled={!dirty || missingModules || missingMode || missingKind || pending}
        >
          {pending ? "Guardando…" : "Guardar acceso"}
        </Button>
      </div>
      {pendingAgents.length > 0 ? (
        <Callout tone="info">
          <p>{AGENT_PENDING_PROMOTION}</p>
          <ul className="mt-1 grid gap-1">
            {pendingAgents.map((a) => (
              <li key={a.agent_id} className="min-w-0">
                <Link
                  href={`/tenants/${tenantId}/agent?agent=${encodeURIComponent(a.agent_id)}`}
                  className="rounded-sm text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {`${a.name}, versión ${a.version}`}
                </Link>
              </li>
            ))}
          </ul>
        </Callout>
      ) : null}
      <ConfirmDialog
        open={live.open}
        onOpenChange={(open) => {
          if (!open) keepMode();
        }}
        title="¿Cambiar el modo de Reservas?"
        description={liveReservationsText(live.count)}
        confirmLabel="Cancelarlas y cambiar"
        cancelLabel="No cambiar"
        destructive
        onConfirm={() => send("cancel_and_notify")}
        error={liveError ?? undefined}
      />
    </div>
  );
}

/**
 * Spec 043 (R1.2): the mode, and in Aforo the kind. Before the first
 * activation the kind shows the values the API will start with; on a client
 * already in Aforo a new kind only renames things (the numbers are the
 * business's, contracts/admin-api.md).
 */
function ReservasFields({
  mode,
  kind,
  stored,
  disabled,
  onMode,
  onKind,
}: {
  mode: ReservasMode | null;
  kind: CapacityKind | null;
  stored: ClientReservasOut | null;
  disabled: boolean;
  onMode: (m: ReservasMode) => void;
  onKind: (k: CapacityKind | null) => void;
}) {
  const modeMissing = mode === null;
  const kindMissing = mode === "capacity" && kind === null;
  const alreadyCapacity = stored?.mode === "capacity";
  const kindNote =
    kind === null
      ? null
      : alreadyCapacity
        ? kind !== stored.capacity_kind
          ? "Cambiar el tipo solo cambia las palabras: aforo, estancia y guardadas siguen como las dejó el negocio."
          : null
        : `Valores de partida: ${kindPreview(kind)}`;
  const kindDescribedBy = [kindMissing ? "reservas-kind-error" : null, kindNote ? "reservas-kind-note" : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="grid min-w-0 gap-4 pl-7">
      <fieldset
        className="grid min-w-0 gap-2"
        disabled={disabled}
        aria-describedby={modeMissing ? "reservas-mode-error" : undefined}
      >
        <legend className="mb-1 text-sm font-medium">Cómo reserva el negocio</legend>
        {RESERVAS_MODES.map((o) => (
          <label key={o.mode} className="flex min-h-6 items-start gap-3 text-sm">
            <input
              type="radio"
              name="reservas-mode"
              value={o.mode}
              checked={mode === o.mode}
              onChange={() => onMode(o.mode)}
              className="mt-1 size-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            />
            <span className="min-w-0 text-pretty">
              <span className="font-medium">{o.label}</span>{" "}
              <span className="text-muted-foreground">— {o.help}</span>
            </span>
          </label>
        ))}
        {modeMissing ? (
          <p id="reservas-mode-error" className="text-xs text-destructive">
            Elige cómo reserva el negocio.
          </p>
        ) : null}
      </fieldset>
      {mode === "capacity" ? (
        <div className="grid min-w-0 gap-2">
          <Label htmlFor="reservas-kind" className="text-sm font-medium">
            Tipo de negocio
          </Label>
          <NativeSelect
            id="reservas-kind"
            value={kind ?? ""}
            onChange={(e) => onKind(e.target.value === "" ? null : (e.target.value as CapacityKind))}
            disabled={disabled}
            required
            aria-invalid={kindMissing || undefined}
            aria-describedby={kindDescribedBy || undefined}
            wrapperClassName="w-full sm:max-w-xs"
          >
            <option value="" disabled>
              Elige el tipo
            </option>
            {CAPACITY_KIND_ORDER.map((k) => (
              <option key={k} value={k}>
                {CAPACITY_KINDS[k].label}
              </option>
            ))}
          </NativeSelect>
          {kindMissing ? (
            <p id="reservas-kind-error" className="text-xs text-destructive">
              Elige el tipo de negocio.
            </p>
          ) : null}
          {kindNote ? (
            <p id="reservas-kind-note" className="text-xs text-muted-foreground text-pretty">
              {kindNote}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Row({
  id,
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(v) => onChange(v === true)}
        disabled={disabled}
        aria-describedby={`${id}-desc`}
        className="mt-1"
      />
      <div className="min-w-0 flex-1">
        <Label htmlFor={id} className={"text-sm font-medium " + (disabled ? "text-muted-foreground" : "")}>
          {label}
        </Label>
        <p id={`${id}-desc`} className="mt-1 text-xs text-muted-foreground text-pretty">
          {description}
        </p>
      </div>
    </div>
  );
}
