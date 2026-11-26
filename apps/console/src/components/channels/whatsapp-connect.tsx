"use client";

import { MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Label, NativeSelect } from "@nexus/ui";

import { listCatalogsAction, whatsappSignupAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { CatalogList, WhatsAppSignupResult } from "@/lib/backend/channels";
import { actionErrorText } from "@/lib/action-error";
import { SignupError, loginWithMeta, type SignupErrorCode, type SignupMode, type SignupVersion } from "@/lib/meta-fb-sdk";

import { CatalogPicker, offerCatalogAfterSignup } from "./catalog-picker";

/** Meta Embedded Signup config handed down by the server component (env). */
export type MetaSignupConfig = {
  appId: string | null;
  graphVersion: string;
  /** Spec 050: which Embedded Signup Meta renders (`v4` until v5 passes staging). */
  signupVersion?: SignupVersion;
  configIdCloudApi: string | null;
  configIdCoexistence: string | null;
};

/**
 * The console, dimmed in Auphere's dark green while Meta's window is open.
 *
 * What is inside that window is Meta's and cannot be styled; what can is
 * everything around it. Without this, the popup floats over a busy console
 * and the eye does not know which of the two is asking for attention.
 */
export function MetaWindowVeil({ open, note, onCancel }: { open: boolean; note?: MessageKey; onCancel?: () => void }) {
  const t = useT();
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const veilRef = React.useRef<HTMLDivElement>(null);
  const backTo = React.useRef<HTMLElement | null>(null);
  const cancellable = open && !!onCancel;
  // Spec 049, 7.2: si la ventana de Meta se queda detrás de otras, la consola
  // no puede quedarse bloqueada. «Cancelar» y Escape quitan la espera. El foco
  // pasa al botón (lo de detrás queda tapado, WCAG 2.4.11) y vuelve después.
  React.useEffect(() => {
    if (!cancellable) return;
    backTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir o cerrar la espera
  }, [cancellable]);

  // Cuando «Cancelar» se va con el foco dentro (empieza el canje con la API),
  // el foco pasa al velo en vez de caer en la página (047 T101, WCAG 2.4.3).
  React.useEffect(() => {
    if (open && !onCancel && document.activeElement === document.body) veilRef.current?.focus();
  }, [open, onCancel]);

  function cancel() {
    onCancel?.();
    if (backTo.current?.isConnected) backTo.current.focus();
  }

  if (!open) return null;
  return (
    <div
      ref={veilRef}
      tabIndex={-1}
      data-slot="meta-window-veil"
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-2 bg-dark-green/95 px-6 text-center text-pistachio outline-none"
    >
      <div role="status" aria-live="polite" className="flex flex-col items-center gap-2">
        <p className="text-lg font-medium text-balance">{t("ch.connect.veil.title")}</p>
        <p className="max-w-md text-sm text-pretty text-pistachio/80">{t("ch.connect.veil.body")}</p>
        {note ? <p className="max-w-md text-sm text-pretty text-pistachio/80">{t(note)}</p> : null}
      </div>
      {onCancel ? (
        <Button ref={cancelRef} type="button" variant="on-dark" className="mt-4" onClick={cancel}>
          {t("common.cancel")}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Pure: the sentence for a refused signup, or null when the generic backend
 * text applies. Two refusals have their own: the number is live somewhere
 * else (R1.4, and it never says where), and Meta still holds it in its
 * previous owner's account (spec 021 R4.2) — the second one is not a console
 * failure, and the copy must not read like one.
 */
export function signupFailureKey(code: string | null | undefined): MessageKey | null {
  if (code === "number_in_use") return "ch.connect.numberInUse";
  if (code === "number_held_by_previous_owner") return "ch.connect.heldByPreviousOwner";
  return null;
}

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const SDK_FAILURE_KEY = {
  sdk_failed: "ch.connect.sdkFailed",
  cancelled: "ch.connect.cancelled",
  timeout: "ch.connect.timeout",
  no_code: "ch.connect.noCode",
  meta_error: "common.error.backend",
  no_number: "ch.connect.noNumber",
  grant_only: "ch.connect.grantOnly",
} as const satisfies Record<SignupErrorCode, MessageKey>;

/** What the whole signup ended in: the new number, or why not (`code`) in words (`text`). */
export type WhatsAppSignupOutcome = { ok: true; data: WhatsAppSignupResult } | { ok: false; code: string; text: string };

/**
 * What the caller can do while Meta's window is open (spec 049, 7.2,
 * 2026-11-26): cancel the wait (`signal`), and hear when the window gave its
 * answer (`onMetaDone`). From then on the code is being exchanged with the
 * API and the wait can no longer be cancelled.
 */
export type SignupWait = { signal?: AbortSignal; onMetaDone?: () => void };

/** «Se cerró la ventana de Meta. No se conectó nada…»: closing the window is not a failure. */
function closedText(t: T): string {
  return `${t("channels.proto.veil.closed")}. ${t("channels.proto.veil.closed.body")}`;
}

/**
 * The Embedded Signup without its buttons: Meta's window with the config id
 * of `mode`, then the code and the WABA ids to the console API. Shared by the
 * client's Channels page and the agent's Canales tab (spec 047, H4), so there
 * is one way to connect a number. Never throws.
 *
 * A cancelled attempt never reaches the API, even if Meta answers later.
 */
export async function runWhatsAppSignup({
  refId,
  meta,
  mode,
  t,
  signal,
  onMetaDone,
}: { refId: string; meta: MetaSignupConfig; mode: SignupMode; t: T } & SignupWait): Promise<WhatsAppSignupOutcome> {
  const configId = mode === "coexistence" ? meta.configIdCoexistence : meta.configIdCloudApi;
  if (!meta.appId || !configId) return { ok: false, code: "not_configured", text: t("ch.connect.byAuphere.body") };
  try {
    const envelope = await loginWithMeta({ appId: meta.appId, version: meta.graphVersion, configId, mode, signupVersion: meta.signupVersion, signal });
    if (signal?.aborted) return { ok: false, code: "cancelled", text: closedText(t) };
    onMetaDone?.();
    const res = await whatsappSignupAction({ ref: refId, mode, ...envelope });
    if (res.ok) return { ok: true, data: res.data };
    // R1.4 / R4.2: the number is someone else's, or its previous owner
    // still holds it at Meta — say so, not «error».
    const key = signupFailureKey(res.code);
    if (key) return { ok: false, code: res.code ?? "backend", text: t(key) };
    // The quota 409 carries the API's English detail: never shown as is.
    if (res.status === 409) return { ok: false, code: "quota", text: t("channels.proto.error.quota") };
    return { ok: false, code: res.code ?? "backend", text: actionErrorText(res, t) };
  } catch (err) {
    const code = err instanceof SignupError ? err.code : "meta_error";
    return { ok: false, code, text: code === "cancelled" ? closedText(t) : t(SDK_FAILURE_KEY[code]) };
  }
}

/**
 * "Connect WhatsApp" — opens Meta's popup (FB.login with our config id),
 * waits for code + WABA ids, posts them to the console API. Disabled with
 * the reason when the client's channel quota is full. The page only renders
 * it when Meta is configured (``connectChoice``); without keys the note
 * ``WhatsAppConnectByAuphere`` takes its place (spec 016, R1.3).
 */
export function WhatsAppConnect({
  refId,
  meta,
  canConnect,
  used,
  max,
  variant = "default",
}: {
  refId: string;
  meta: MetaSignupConfig;
  canConnect: boolean;
  used: number;
  max: number;
  variant?: "default" | "outline";
}) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [mode, setMode] = React.useState<SignupMode>(meta.configIdCloudApi ? "cloud_api" : "coexistence");
  const [working, setWorking] = React.useState(false);
  // Spec 049, 7.2 (enmienda del 2026-11-26): mientras la ventana de Meta está
  // abierta se puede cancelar, como en Instagram y Messenger. Cada intento
  // lleva su número y su `AbortController`: lo que Meta devuelva a uno
  // cancelado no llega a la API. Al canjear el código ya no se cancela.
  const [waitingMeta, setWaitingMeta] = React.useState(false);
  const attempt = React.useRef(0);
  const abort = React.useRef<AbortController | null>(null);
  React.useEffect(() => () => abort.current?.abort(), []);
  // Historia 2 (spec 022): al terminar el alta, si el negocio tiene catálogo,
  // se ofrece aquí mismo; se puede saltar, y la tarjeta lo vuelve a ofrecer.
  const [offer, setOffer] = React.useState<{ channelId: string; list: CatalogList } | null>(null);
  // Spec 063 (2.1; 047, 30.6): al terminar, la configuración del número nuevo.
  const configOf = (channelId: string) => `/clients/${encodeURIComponent(refId)}/channels/${encodeURIComponent(channelId)}`;
  const configId = mode === "coexistence" ? meta.configIdCoexistence : meta.configIdCloudApi;
  const disabledReason = !canConnect ? t("ch.quota.full", { used, max }) : null;

  async function start() {
    if (!meta.appId || !configId) return;
    abort.current?.abort();
    const mine = ++attempt.current;
    const controller = new AbortController();
    abort.current = controller;
    setWorking(true);
    setWaitingMeta(true);
    try {
      const res = await runWhatsAppSignup({
        refId,
        meta,
        mode,
        t,
        signal: controller.signal,
        onMetaDone: () => attempt.current === mine && setWaitingMeta(false),
      });
      if (attempt.current !== mine) return;
      // Closing Meta's window is not an error: said plainly, the dialog stays to try again.
      if (!res.ok) return void (res.code === "cancelled" ? toast(res.text) : toast.error(res.text));
      // R1.2: the card, the list and the onboarding are recomputed on the
      // server; the toast says what changed for the client right now.
      toast.success(
        res.data.client_status === "active" ? t("ch.connect.done.active", { phone: res.data.display_phone_number }) : t("ch.connect.done", { phone: res.data.display_phone_number }),
      );
      setOpen(false);
      router.refresh();
      const list = await listCatalogsAction({ ref: refId, channelId: res.data.channel_id });
      if (offerCatalogAfterSignup(list) && list.ok) setOffer({ channelId: res.data.channel_id, list: list.data });
      else router.push(configOf(res.data.channel_id));
    } catch {
      if (attempt.current === mine) toast.error(t("common.error.backend"));
    } finally {
      if (attempt.current === mine) {
        abort.current = null;
        setWorking(false);
        setWaitingMeta(false);
      }
    }
  }

  const cancelWait = React.useCallback(() => {
    attempt.current += 1;
    abort.current?.abort();
    abort.current = null;
    setWorking(false);
    setWaitingMeta(false);
  }, []);

  return (
    <>
      <span title={disabledReason ?? undefined} className="inline-flex">
        <Button variant={variant} onClick={() => setOpen(true)} disabled={!!disabledReason} aria-describedby={disabledReason ? "ch-connect-reason" : undefined}>
          <MessageCircle aria-hidden="true" />
          {used > 0 ? t("ch.connect.another") : t("ch.connect")}
        </Button>
      </span>
      {disabledReason ? (
        <p id="ch-connect-reason" className="text-xs text-muted-foreground">
          {disabledReason}
        </p>
      ) : null}
      <MetaWindowVeil open={working} onCancel={waitingMeta ? cancelWait : undefined} />
      {offer ? (
        <CatalogPicker
          key={offer.channelId}
          refId={refId}
          channelId={offer.channelId}
          current={null}
          open
          onOpenChange={(o) => {
            if (o) return;
            setOffer(null);
            router.push(configOf(offer.channelId));
          }}
          offer
          preloaded={offer.list}
        />
      ) : null}
      {/* While Meta's window is open the veil takes over: the dialog steps
          aside (and does not pull the focus back) so «Cancelar» and Escape
          belong to the veil, and it comes back when the wait is cancelled. */}
      <Dialog open={open && !working} onOpenChange={(o) => !working && setOpen(o)}>
        <DialogContent finalFocus={!working}>
          <DialogHeader>
            <DialogTitle>{t("ch.connect")}</DialogTitle>
            <DialogDescription>{t("ch.connect.help")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="ch-mode">{t("ch.connect.mode")}</Label>
            <NativeSelect id="ch-mode" wrapperClassName="w-full" value={mode} onChange={(e) => setMode(e.target.value as SignupMode)} disabled={working}>
              {meta.configIdCloudApi ? <option value="cloud_api">{t("ch.connect.mode.cloud_api")}</option> : null}
              {meta.configIdCoexistence ? <option value="coexistence">{t("ch.connect.mode.coexistence")}</option> : null}
            </NativeSelect>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={working}>
              {t("common.cancel")}
            </Button>
            <Button onClick={start} disabled={working || !configId} aria-busy={working}>
              {working ? t("ch.connect.working") : t("ch.connect.start")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
