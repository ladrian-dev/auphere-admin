"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Checkbox, ConfirmDialog, ErrorState, Label, NativeSelect, Section, Switch } from "@nexus/ui";

import { setClientAccessAction } from "@/app/(console)/clients/[ref]/access/actions";
import { agentHref } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import {
  ACCESS_MODULES,
  CAPACITY_KINDS,
  type AccessModule,
  type CapacityKind,
  type ClientAccess,
  type ReservasMode,
} from "@/lib/backend/client-access";

import { accessBody, accessErrorKey, accessIsDirty, orderedModules, type AccessDraft } from "./access-model";

type Props = {
  refId: string;
  /** `null`: no se pudo leer (el estado de error, con Reintentar). */
  access: ClientAccess | null;
  onSaved: (access: ClientAccess) => void;
  onRetry: () => void;
  retrying?: boolean;
};

/**
 * Spec 056 (requisito 3.3) — «Consola del cliente»: el interruptor y los módulos
 * Panel, Bandeja, Reservas (con su modo) y Consumo, con las reglas del panel. La
 * API decide; aquí solo se evita mandar lo que ya se sabe que dirá que no.
 *
 * Los cinco estados: cargando (`loading.tsx` de la ruta, y «Guardando» al
 * guardar), vacío (nunca se encendió), error (Reintentar), parcial (un cliente
 * archivado, de solo lectura) e ideal.
 */
export function ClientConsoleCard({ refId, access, onSaved, onRetry, retrying = false }: Props) {
  const t = useT();
  if (!access) {
    return (
      <Section title={t("clientAccess.console.title")} data-slot="client-console-card" data-state="error">
        <ErrorState
          title={t("clientAccess.load.error")}
          description={t("clientAccess.load.error.hint")}
          onRetry={retrying ? undefined : onRetry}
          retryLabel={t("clientAccess.retry")}
        />
      </Section>
    );
  }
  // Una clave por lectura: lo guardado vuelve a ser el punto de partida.
  return <ConsoleForm key={`${access.enabled}:${access.modules.join(",")}:${access.reservas?.mode ?? ""}`} refId={refId} access={access} onSaved={onSaved} />;
}

function ConsoleForm({ refId, access, onSaved }: { refId: string; access: ClientAccess; onSaved: (a: ClientAccess) => void }) {
  const t = useT();
  const stored = access.reservas ?? null;
  const [enabled, setEnabled] = React.useState(access.enabled);
  const [modules, setModules] = React.useState<Set<string>>(() => new Set(access.modules));
  const [mode, setMode] = React.useState<ReservasMode | null>(stored?.mode ?? null);
  const [kind, setKind] = React.useState<CapacityKind | null>(stored?.capacity_kind ?? null);
  const [pending, startTransition] = React.useTransition();
  const [error, setError] = React.useState<string | null>(null);
  const [live, setLive] = React.useState<{ open: boolean; count: number | null }>({ open: false, count: null });
  const [liveError, setLiveError] = React.useState<string | null>(null);

  if (!access.eligible) {
    // Parcial: se lee, no se cambia (un cliente archivado no se abre a nadie).
    return (
      <Section
        title={t("clientAccess.console.title")}
        description={t("clientAccess.console.description")}
        data-slot="client-console-card"
        data-state="partial"
      >
        <Callout tone="warning" title={t(accessErrorKey(access.ineligible_reason))}>
          {access.enabled ? t("clientAccess.console.readonly.on", { modules: moduleNames(t, access.modules) }) : t("clientAccess.console.readonly.off")}
        </Callout>
      </Section>
    );
  }

  const draft: AccessDraft = { enabled, modules, mode, kind };
  const withReservas = modules.has("reservas");
  const missingModules = enabled && orderedModules(modules).length === 0;
  const missingMode = withReservas && mode === null;
  const missingKind = withReservas && mode === "capacity" && kind === null;
  const dirty = accessIsDirty(access, draft);
  const inboxLocked = !access.whatsapp_connected && !access.modules.includes("inbox");
  const modeChanges = withReservas && stored !== null && mode !== null && mode !== stored.mode;
  const pendingAgents = stored?.agents_pending_promotion ?? [];
  const otherCalendar = withReservas ? (stored?.agents_with_other_calendar ?? []) : [];
  const empty = !access.enabled && access.modules.length === 0;

  function toggle(m: AccessModule, on: boolean) {
    setModules((prev) => {
      const next = new Set(prev);
      if (on) next.add(m);
      else next.delete(m);
      return next;
    });
  }

  async function send(onLive?: "cancel_and_notify") {
    setError(null);
    const res = await setClientAccessAction({ ref: refId, ...accessBody(access, draft, onLive) });
    if (!res.ok) {
      // Alguien reservó mientras tanto: la misma decisión, con la cuenta de la API.
      if (res.code === "live_reservations" && !onLive) {
        setLiveError(null);
        setLive({ open: true, count: typeof res.info?.count === "number" ? res.info.count : null });
        return;
      }
      const text = t(accessErrorKey(res.code));
      if (onLive) setLiveError(text);
      else setError(text);
      return;
    }
    setLive({ open: false, count: null });
    toast.success(
      !res.data.enabled ? t("clientAccess.console.saved.off") : onLive ? t("clientAccess.console.saved.modeChanged") : t("clientAccess.console.saved"),
    );
    onSaved(res.data);
  }

  function onSave() {
    if (modeChanges && stored.live_future > 0) {
      setLiveError(null);
      setLive({ open: true, count: stored.live_future });
      return;
    }
    startTransition(() => send());
  }

  /** «No cambiar»: vuelve el modo guardado y el resto del formulario se queda. */
  function keepMode() {
    setLive((prev) => ({ ...prev, open: false }));
    setLiveError(null);
    setMode(stored?.mode ?? null);
    setKind(stored?.capacity_kind ?? null);
  }

  return (
    <Section
      title={t("clientAccess.console.title")}
      description={t("clientAccess.console.description")}
      data-slot="client-console-card"
      data-state={empty ? "empty" : "ideal"}
      aria-busy={pending || undefined}
    >
      {empty ? <Callout tone="neutral">{t("clientAccess.console.empty")}</Callout> : null}
      <div className="flex min-w-0 items-start gap-3">
        <Switch id="client-console-on" checked={enabled} onCheckedChange={(v) => setEnabled(v === true)} aria-describedby="client-console-on-desc" className="mt-1" />
        <div className="grid min-w-0 flex-1 gap-1">
          <Label htmlFor="client-console-on" className="text-sm font-medium">
            {t("clientAccess.console.on")}
          </Label>
          <p id="client-console-on-desc" className="text-sm text-pretty text-muted-foreground">
            {t("clientAccess.console.on.hint")}
          </p>
        </div>
      </div>
      <fieldset className="grid min-w-0 gap-4 border-l border-border pl-4">
        <legend className="mb-2 text-sm font-medium">{t("clientAccess.modules")}</legend>
        {ACCESS_MODULES.map((m) => {
          const locked = m === "inbox" && inboxLocked;
          return (
            <div key={m} className="grid min-w-0 gap-3">
              <div className="flex min-w-0 items-start gap-3">
                <Checkbox
                  id={`client-module-${m}`}
                  checked={modules.has(m)}
                  onCheckedChange={(v) => toggle(m, v === true)}
                  disabled={locked || pending}
                  aria-describedby={`client-module-${m}-desc`}
                  className="mt-1"
                />
                <div className="grid min-w-0 flex-1 gap-1">
                  <Label htmlFor={`client-module-${m}`} className={locked ? "text-sm font-medium text-muted-foreground" : "text-sm font-medium"}>
                    {t(`clientAccess.module.${m}` as MessageKey)}
                  </Label>
                  <p id={`client-module-${m}-desc`} className="text-sm text-pretty text-muted-foreground">
                    {locked ? t("clientAccess.module.inbox.locked") : t(`clientAccess.module.${m}.hint` as MessageKey)}
                  </p>
                </div>
              </div>
              {m === "reservas" && withReservas ? (
                <ReservasFields mode={mode} kind={kind} stored={stored} disabled={pending} onMode={setMode} onKind={setKind} />
              ) : null}
            </div>
          );
        })}
      </fieldset>
      {missingModules ? (
        <p className="text-sm text-destructive" role="alert">
          {t("clientAccess.error.no_modules")}
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-destructive text-pretty" role="alert">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button type="button" onClick={onSave} loading={pending} disabled={!dirty || missingModules || missingMode || missingKind || pending}>
          {pending ? t("clientAccess.console.saving") : t("clientAccess.console.save")}
        </Button>
      </div>
      {pendingAgents.length > 0 ? (
        <Callout tone="info" title={t("clientAccess.reservas.pendingAgents")}>
          <ul className="grid gap-1">
            {pendingAgents.map((a) => (
              <li key={a.agent_id} className="min-w-0">
                <Link href={agentHref(refId, a.agent_id)} className="rounded-sm break-words underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
                  {t("clientAccess.reservas.agentVersion", { name: a.name, version: String(a.version) })}
                </Link>
              </li>
            ))}
          </ul>
        </Callout>
      ) : null}
      {otherCalendar.length > 0 ? (
        <Callout tone="info" title={t("clientAccess.reservas.otherCalendar")}>
          <ul className="grid gap-1">
            {otherCalendar.map((a) => (
              <li key={a.agent_id} className="min-w-0">
                <Link href={agentHref(refId, a.agent_id)} className="rounded-sm break-words underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
                  {a.name}
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
        title={t("clientAccess.live.title")}
        description={live.count === null ? t("clientAccess.live.body") : t(live.count === 1 ? "clientAccess.live.body.one" : "clientAccess.live.body.other", { n: String(live.count) })}
        confirmLabel={t("clientAccess.live.confirm")}
        cancelLabel={t("clientAccess.live.keep")}
        destructive
        onConfirm={() => send("cancel_and_notify")}
        error={liveError ?? undefined}
      />
    </Section>
  );
}

function moduleNames(t: ReturnType<typeof useT>, modules: readonly string[]): string {
  return ACCESS_MODULES.filter((m) => modules.includes(m))
    .map((m) => t(`clientAccess.module.${m}` as MessageKey))
    .join(", ");
}

/**
 * El modo de Reservas y, en Aforo, el tipo de negocio. La primera vez se elige;
 * después, cambiarlo con reservas futuras pregunta antes (el diálogo de arriba).
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
  stored: ClientAccess["reservas"] | null;
  disabled: boolean;
  onMode: (m: ReservasMode) => void;
  onKind: (k: CapacityKind | null) => void;
}) {
  const t = useT();
  const modeMissing = mode === null;
  const kindMissing = mode === "capacity" && kind === null;
  const renames = stored?.mode === "capacity" && kind !== null && kind !== stored.capacity_kind;
  return (
    <div className="grid min-w-0 gap-4 pl-7">
      <fieldset className="grid min-w-0 gap-2" disabled={disabled} aria-describedby={modeMissing ? "client-reservas-mode-error" : undefined}>
        <legend className="mb-1 text-sm font-medium">{t("clientAccess.reservas.mode")}</legend>
        {(["services", "capacity"] as const).map((m) => (
          <label key={m} className="flex min-h-6 min-w-0 items-start gap-3 text-sm">
            <input
              type="radio"
              name="client-reservas-mode"
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
          <p id="client-reservas-mode-error" className="text-xs text-destructive">
            {t("clientAccess.error.reservas_mode_required")}
          </p>
        ) : null}
      </fieldset>
      {mode === "capacity" ? (
        <div className="grid min-w-0 gap-2">
          <Label htmlFor="client-reservas-kind" className="text-sm font-medium">
            {t("clientAccess.reservas.kind")}
          </Label>
          <NativeSelect
            id="client-reservas-kind"
            value={kind ?? ""}
            onChange={(e) => onKind(e.target.value === "" ? null : (e.target.value as CapacityKind))}
            disabled={disabled}
            required
            aria-invalid={kindMissing || undefined}
            aria-describedby={kindMissing ? "client-reservas-kind-error" : renames ? "client-reservas-kind-note" : undefined}
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
            <p id="client-reservas-kind-error" className="text-xs text-destructive">
              {t("clientAccess.error.reservas_kind_required")}
            </p>
          ) : null}
          {renames ? (
            <p id="client-reservas-kind-note" className="text-xs text-pretty text-muted-foreground">
              {t("clientAccess.reservas.kind.renames")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
