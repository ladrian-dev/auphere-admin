"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, ConfirmDialog, StatusBadge, formatDateTime } from "@nexus/ui";

import { MetaWindowVeil, type SignupWait } from "@/components/channels/whatsapp-connect";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AdMeasurement, AdMeasurementIn } from "@/lib/backend/channel-config-types";

import type { Result } from "./builder-model";

/** Lo que la API deja como último error del número (`contracts/api-y-eventos.md` §2.1 y §4), en qué hacer. */
const ERROR_KEYS: Record<string, MessageKey> = {
  reauthorize: "builder.channel.ads.error.reauthorize",
  page_required: "builder.channel.ads.error.page_required",
  too_old: "builder.channel.ads.error.too_old",
  no_identity: "builder.channel.ads.error.no_identity",
  meta_unavailable: "builder.channel.ads.error.meta_unavailable",
};

/** El texto de qué hacer para un código; uno desconocido (`meta_<n>`) dice lo general. */
export function adErrorKey(code: string): MessageKey {
  return ERROR_KEYS[code] ?? "builder.channel.ads.error.other";
}

export type ReconnectOutcome = { ok: true } | { ok: false; text: string };

const STATE: Record<string, { tone: "positive" | "muted" | "warning"; key: MessageKey }> = {
  on: { tone: "positive", key: "builder.channel.ads.state.on" },
  off: { tone: "muted", key: "builder.channel.ads.state.off" },
  reauthorize: { tone: "warning", key: "builder.channel.ads.state.reauthorize" },
};

/**
 * Spec 076 (requisito 4): que el número le diga a Meta los resultados que
 * consigue el agente, para que los anuncios del cliente aprendan.
 *
 * - Activar abre una confirmación que dice qué sale a Meta y pide que el
 *   negocio pueda enviarlo (4.8). Sin marcarla no se activa.
 * - Si el token del número no tiene el permiso de eventos, la API responde
 *   `reauthorize` y la sección pide «Volver a conectar» (4.3). Volver a conectar
 *   no enciende nada: al terminar, se vuelve a pedir la confirmación, que es lo
 *   que comprueba el permiso.
 * - Se ven el estado, el conjunto de datos, lo enviado en 7 días y el último
 *   error con qué hacer (4.6).
 * - Apagar descarta lo que estaba en cola (4.4) y se dice antes.
 *
 * Solo se monta si la API manda el bloque (4.7). Quien solo lee lo ve como
 * texto (§V).
 */
export function AdMeasurementSection({
  measurement,
  canWrite,
  onSave,
  onReconnect,
  paused = false,
}: {
  measurement: AdMeasurement;
  canWrite: boolean;
  onSave: (body: AdMeasurementIn) => Promise<Result<AdMeasurement>>;
  /**
   * El alta de Meta con `reconnect_config_id`. Sin él (sin claves de Meta), «Volver a conectar» no se ofrece.
   * `signal` cancela la espera de la ventana de Meta y `onMetaDone` avisa de que empieza el canje (049, 7.2).
   */
  onReconnect?: (wait: Required<SignupWait>) => Promise<ReconnectOutcome>;
  /** El número está en pausa: volver a conectarlo lo reanudaría, así que antes hay que reanudarlo. */
  paused?: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const [m, setM] = React.useState(measurement);
  const [asking, setAsking] = React.useState(false);
  const [agreed, setAgreed] = React.useState(false);
  const [dialogError, setDialogError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<"off" | "reconnect" | null>(null);
  // Spec 049, 7.2 (enmienda del 2026-11-26): la espera de la ventana de Meta al
  // volver a conectar se cancela, como en Instagram y Messenger. Cada intento
  // lleva su número; lo que devuelva uno cancelado se descarta.
  const [waitingMeta, setWaitingMeta] = React.useState(false);
  const attempt = React.useRef(0);
  const abort = React.useRef<AbortController | null>(null);
  React.useEffect(() => () => abort.current?.abort(), []);
  const agreeId = React.useId();

  const state = STATE[m.state] ?? STATE.off!;
  const reauthorize = m.state === "reauthorize";
  const error = !reauthorize && m.last_error ? m.last_error : null;

  function ask() {
    setAgreed(false);
    setDialogError(null);
    setAsking(true);
  }

  async function enable() {
    setDialogError(null);
    const res = await onSave({ enabled: true, confirm_data_sharing: true });
    if (res.ok) {
      setM(res.data);
      setAsking(false);
      toast.success(t("builder.channel.ads.on.done"));
      return;
    }
    if (res.code === "reauthorize") {
      // La API dejó la marca guardada: la página dice «Volver a conectar» desde ahora.
      setM((prev) => ({ ...prev, state: "reauthorize", enabled: false, last_error: { code: "reauthorize", at: null, hint: "reauthorize" } }));
      setAsking(false);
      return;
    }
    setDialogError(t(res.code === "meta_unavailable" ? "builder.channel.ads.error.meta_unavailable" : "builder.channel.error"));
  }

  async function disable() {
    setBusy("off");
    const res = await onSave({ enabled: false, confirm_data_sharing: false });
    setBusy(null);
    if (res.ok) {
      setM(res.data);
      toast.success(t("builder.channel.ads.off.done"));
      return;
    }
    toast.error(t("builder.channel.error"));
  }

  async function reconnect() {
    if (!onReconnect) return;
    abort.current?.abort();
    const mine = ++attempt.current;
    const controller = new AbortController();
    abort.current = controller;
    setBusy("reconnect");
    setWaitingMeta(true);
    const res = await onReconnect({ signal: controller.signal, onMetaDone: () => attempt.current === mine && setWaitingMeta(false) });
    if (attempt.current !== mine) return;
    abort.current = null;
    setBusy(null);
    setWaitingMeta(false);
    if (!res.ok) {
      toast.error(res.text);
      return;
    }
    toast.success(t("builder.channel.ads.reconnect.done"));
    ask();
  }

  function cancelWait() {
    attempt.current += 1;
    abort.current?.abort();
    abort.current = null;
    setBusy(null);
    setWaitingMeta(false);
  }

  const facts = (
    <dl className="grid min-w-0 gap-2 text-sm">
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        <dt className="sr-only">{t("builder.channel.ads.state")}</dt>
        <dd>
          <StatusBadge tone={state.tone}>{t(state.key)}</StatusBadge>
        </dd>
      </div>
      {m.enabled || m.dataset_linked ? (
        <div className="grid min-w-0 gap-1 min-[480px]:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
          <dt className="text-muted-foreground">{t("builder.channel.ads.dataset")}</dt>
          <dd>{t(m.dataset_linked ? "builder.channel.ads.dataset.linked" : "builder.channel.ads.dataset.none")}</dd>
        </div>
      ) : null}
      {m.enabled ? (
        <div className="grid min-w-0 gap-1 min-[480px]:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
          <dt className="text-muted-foreground">{t("builder.channel.ads.sent7d")}</dt>
          <dd className="tabular-nums">{m.sent_7d}</dd>
        </div>
      ) : null}
    </dl>
  );

  return (
    <div className="grid min-w-0 gap-4" data-slot="ad-measurement">
      {facts}

      {reauthorize ? (
        <Callout
          tone="warning"
          title={t("builder.channel.ads.reauthorize.title")}
          action={
            canWrite && onReconnect ? (
              <Button type="button" size="sm" loading={busy === "reconnect"} onClick={() => void reconnect()}>
                {t("builder.channel.ads.reconnect")}
              </Button>
            ) : undefined
          }
        >
          {t(
            canWrite && onReconnect
              ? "builder.channel.ads.reauthorize.body"
              : canWrite && paused
                ? "builder.channel.ads.reauthorize.paused"
                : "builder.channel.ads.reauthorize.readonly",
          )}
        </Callout>
      ) : null}

      {error ? (
        <Callout tone="warning" title={t("builder.channel.ads.error.title")}>
          <span className="block text-pretty">{t(adErrorKey(error.hint || error.code))}</span>
          {error.at ? <span className="block text-muted-foreground">{formatDateTime(error.at, locale)}</span> : null}
        </Callout>
      ) : null}

      {canWrite ? (
        <div className="flex min-w-0 flex-wrap gap-2">
          {m.enabled ? (
            <Button type="button" variant="outline" className="w-fit" loading={busy === "off"} onClick={() => void disable()}>
              {t("builder.channel.ads.off")}
            </Button>
          ) : (
            <Button type="button" variant={reauthorize ? "outline" : "default"} className="w-fit" onClick={ask}>
              {t(reauthorize ? "builder.channel.ads.retry" : "builder.channel.ads.on")}
            </Button>
          )}
        </div>
      ) : null}
      {canWrite && m.enabled ? <p className="text-pretty text-sm text-muted-foreground">{t("builder.channel.ads.off.hint")}</p> : null}

      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title={t("builder.channel.ads.confirm.title")}
        description={t("builder.channel.ads.confirm.body")}
        confirmLabel={t("builder.channel.ads.on")}
        confirmDisabled={!agreed}
        error={dialogError ?? undefined}
        onConfirm={enable}
      >
        <ul className="grid list-disc gap-1 ps-5 text-sm">
          <li className="text-pretty">{t("builder.channel.ads.confirm.what")}</li>
          <li className="text-pretty">{t("builder.channel.ads.confirm.who")}</li>
          <li className="text-pretty">{t("builder.channel.ads.confirm.never")}</li>
        </ul>
        <label htmlFor={agreeId} className="flex min-w-0 items-start gap-3 text-sm">
          <input
            id={agreeId}
            type="checkbox"
            className="mt-1 size-4 shrink-0 accent-primary"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
          />
          <span className="text-pretty">{t("builder.channel.ads.confirm.agree")}</span>
        </label>
      </ConfirmDialog>
      <MetaWindowVeil open={busy === "reconnect"} onCancel={waitingMeta ? cancelWait : undefined} />
    </div>
  );
}
