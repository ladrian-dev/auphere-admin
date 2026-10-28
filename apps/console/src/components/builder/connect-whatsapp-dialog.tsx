"use client";

import { ArrowLeft, CircleAlert, ExternalLink, Link as LinkIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, StatusBadge, cn } from "@nexus/ui";

import { moveChannelAction } from "@/app/(console)/clients/[ref]/agents/channel-actions";
import { listCatalogsAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { BrandLogo } from "@/components/brand-logo";
import { CatalogPicker, offerCatalogAfterSignup } from "@/components/channels/catalog-picker";
import { metaIsConfigured } from "@/components/channels/connect-choice";
import { runWhatsAppSignup, type MetaSignupConfig, type WhatsAppSignupOutcome } from "@/components/channels/whatsapp-connect";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ChannelPage, PendingOwnerLink } from "@/lib/backend/channel-config-types";
import type { CatalogList, WhatsAppSignupResult } from "@/lib/backend/channels";
import type { SignupMode } from "@/lib/meta-fb-sdk";

import type { Result } from "./builder-model";
import { channelHref, ownerLinkCopy } from "./channel-model";
import { OwnerLinkPanel, type OwnerLinkActions } from "./owner-link-panel";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Lo que hace falta para conectar un número desde el agente. Sin ellas, las de servidor. */
export type ConnectActions = {
  /** El alta de Meta de la consola (`runWhatsAppSignup`): la ventana de Meta y luego la API. */
  signup: (body: { refId: string; meta: MetaSignupConfig; mode: SignupMode; t: T }) => Promise<WhatsAppSignupOutcome>;
  /** El alta deja el número en el cliente: se pasa a este agente (34.2). */
  move: (body: { ref: string; channel: string; to: string }) => Promise<Result<ChannelPage>>;
  catalogs: (body: { ref: string; channelId: string }) => Promise<Result<CatalogList>>;
};

export const CONNECT_ACTIONS: ConnectActions = {
  signup: (body) => runWhatsAppSignup(body),
  move: (body) => moveChannelAction(body),
  catalogs: (body) => listCatalogsAction(body),
};

/** El paso del modal: elegir cómo se conecta, o el enlace para el dueño. */
export type ConnectStage = "method" | "link";

/** Dónde quedó el número: en este agente, o en el principal porque este no se pudo elegir. */
export type Placed = "here" | "elsewhere";

const MODES = ["coexistence", "cloud_api"] as const satisfies readonly SignupMode[];
const IN_USE = new Set(["number_in_use", "number_held_by_previous_owner"]);

type Veil = { mode: SignupMode; failure: { code: string; text: string } | null };

/**
 * «Conectar WhatsApp» como el prototipo aprobado (`agente.md` §10.1, §10.2,
 * hueco H4), sobre lo que la consola ya tenía para conectar un número:
 *
 * - Paso «método»: Coexistencia (recomendado) o Cloud API. «Conectar» abre el
 *   alta insertada de Meta con la configuración de ese modo, la misma de la
 *   página de canales del cliente (`runWhatsAppSignup`). Un modo sin su
 *   configuración en este entorno no se puede elegir, y sin Meta configurado
 *   se dice quién lo conecta (spec 016, R1.3).
 * - Paso «enlace» («Compartir un enlace»): el enlace del dueño de siempre
 *   (`OwnerLinkPanel`, requisito 31), en el modo elegido.
 * - Mientras Meta está abierto, el velo «Continúa en la ventana de Meta»; si
 *   no se conecta, dice por qué y deja intentarlo de nuevo. No ofrece
 *   «Cancelar» ni «Abrir la ventana otra vez»: la ventana de Meta no se puede
 *   cerrar ni reabrir desde aquí, y prometerlo sería mentir.
 * - Al volver: `onConnected` lo deja en este agente; si tiene catálogo se
 *   ofrece (spec 022) y luego se abre la configuración del canal.
 */
export function ConnectWhatsApp({
  refId,
  agentId,
  clientName,
  meta,
  fromPhone,
  stage,
  onStage,
  onVeil,
  onConnected,
  onLinkCreated,
  ownerLinkActions,
  actions = CONNECT_ACTIONS,
}: {
  refId: string;
  agentId: string;
  clientName: string | null;
  meta: MetaSignupConfig | null;
  fromPhone: boolean;
  stage: ConnectStage | null;
  onStage: (stage: ConnectStage | null) => void;
  /** El velo se abre o se cierra (el asistente marca «Conectar» mientras tanto). */
  onVeil?: (open: boolean) => void;
  onConnected: (result: WhatsAppSignupResult) => Promise<Placed>;
  onLinkCreated: (pending: PendingOwnerLink) => void;
  ownerLinkActions?: OwnerLinkActions;
  actions?: ConnectActions;
}) {
  const t = useT();
  const router = useRouter();
  const id = React.useId();
  const configured = meta !== null && metaIsConfigured(meta);
  const available = (m: SignupMode) => configured && Boolean(m === "coexistence" ? meta?.configIdCoexistence : meta?.configIdCloudApi);
  const [mode, setMode] = React.useState<SignupMode>(() => (meta?.configIdCoexistence || !meta?.configIdCloudApi ? "coexistence" : "cloud_api"));
  const [veil, setVeil] = React.useState<Veil | null>(null);
  const [linkCreated, setLinkCreated] = React.useState(false);
  const [offer, setOffer] = React.useState<{ channelId: string; list: CatalogList } | null>(null);
  const name = clientName ?? t("channels.proto.veil.theBusiness");

  function showVeil(next: Veil | null) {
    setVeil(next);
    onVeil?.(next !== null);
  }

  function go(stageNext: ConnectStage | null) {
    setLinkCreated(false);
    onStage(stageNext);
  }

  function configure(channelId: string) {
    router.push(channelHref(refId, agentId, channelId));
  }

  async function start(m: SignupMode) {
    if (!meta || !available(m)) return;
    showVeil({ mode: m, failure: null });
    const out = await actions.signup({ refId, meta, mode: m, t });
    if (!out.ok) return showVeil({ mode: m, failure: { code: out.code, text: out.text } });
    showVeil(null);
    const placed = await onConnected(out.data);
    if (placed === "elsewhere") {
      toast.warning(t("channels.proto.done.elsewhere", { phone: out.data.display_phone_number }));
      return;
    }
    toast.success(t("channels.proto.done"));
    const list = await actions.catalogs({ ref: refId, channelId: out.data.channel_id }).catch(() => null);
    if (list && offerCatalogAfterSignup(list) && list.ok) setOffer({ channelId: out.data.channel_id, list: list.data });
    else configure(out.data.channel_id);
  }

  const failure = veil?.failure ?? null;
  const veilTitle = !failure
    ? t("channels.proto.veil.title")
    : IN_USE.has(failure.code)
      ? t("channels.proto.veil.inUse")
      : failure.code === "cancelled"
        ? t("channels.proto.veil.closed")
        : t("channels.proto.veil.failed");
  const veilBody = !failure
    ? t(`channels.proto.veil.${veil?.mode ?? mode}` as MessageKey, { name })
    : failure.code === "cancelled"
      ? t("channels.proto.veil.closed.body")
      : failure.text;

  return (
    <>
      <Dialog open={stage !== null} onOpenChange={(open) => !open && go(null)}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] gap-5 overflow-y-auto p-6 sm:max-w-140" data-slot="connect-whatsapp">
          {stage === "link" ? (
            <>
              <DialogHeader>
                <DialogTitle className="text-xl leading-tight font-semibold">{t("channels.proto.link.title")}</DialogTitle>
                <DialogDescription className="max-w-prose text-pretty">{t(ownerLinkCopy(fromPhone).body)}</DialogDescription>
              </DialogHeader>
              <OwnerLinkPanel
                bare
                refId={refId}
                agentId={agentId}
                pending={null}
                canWrite
                fromPhone={fromPhone}
                actions={ownerLinkActions}
                initialMode={mode}
                onCreated={(pending) => {
                  setLinkCreated(true);
                  onLinkCreated(pending);
                }}
                onDone={() => go(null)}
              />
              {linkCreated ? null : (
                <DialogFooter className="-mx-6 -mb-6 px-6 py-4 sm:justify-start">
                  <Button variant="ghost" onClick={() => go("method")}>
                    <ArrowLeft aria-hidden="true" />
                    {t("channels.proto.link.back")}
                  </Button>
                </DialogFooter>
              )}
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="text-xl leading-tight font-semibold">{t("channels.proto.connect.title")}</DialogTitle>
                <DialogDescription className="max-w-prose text-pretty">
                  {clientName ? t("channels.proto.connect.body", { name: clientName }) : t("channels.proto.connect.body.noName")}
                </DialogDescription>
              </DialogHeader>
              {configured ? null : <Callout tone="info" title={t("ch.connect.byAuphere.title")}>{t("ch.connect.byAuphere.body")}</Callout>}
              <fieldset className="grid min-w-0 gap-3">
                <legend className="sr-only">{t("channels.proto.connect.modes")}</legend>
                {MODES.map((m) => {
                  const on = available(m);
                  return (
                    <label
                      key={m}
                      className={cn(
                        "flex min-w-0 items-start gap-3 rounded-lg border border-input bg-card p-4 transition-[border-color,box-shadow] duration-150 has-checked:border-primary has-checked:ring-1 has-checked:ring-primary has-focus-visible:ring-2 has-focus-visible:ring-ring motion-reduce:transition-none",
                        on ? "cursor-pointer" : "cursor-not-allowed bg-muted",
                      )}
                    >
                      <input
                        type="radio"
                        name={`${id}-mode`}
                        value={m}
                        checked={mode === m}
                        disabled={!on}
                        onChange={() => setMode(m)}
                        className="mt-1 size-4 shrink-0 accent-primary"
                      />
                      <span className="grid min-w-0 gap-1">
                        <span className="flex flex-wrap items-center gap-2 font-medium">
                          {t(`channels.proto.connect.${m}` as MessageKey)}
                          {m === "coexistence" ? <StatusBadge tone="positive">{t("channels.proto.connect.recommended")}</StatusBadge> : null}
                        </span>
                        <span className="text-sm text-pretty text-muted-foreground">{t(`channels.proto.connect.${m}.hint` as MessageKey)}</span>
                        {configured && !on ? <span className="text-xs text-muted-foreground">{t("channels.proto.connect.off")}</span> : null}
                      </span>
                    </label>
                  );
                })}
              </fieldset>
              <div className="flex min-w-0 items-start gap-3 rounded-lg bg-muted px-4 py-3 text-sm" data-slot="connect-share">
                <LinkIcon aria-hidden="true" className="mt-1 size-4 shrink-0 text-muted-foreground" />
                <p className="min-w-0 text-pretty text-muted-foreground">
                  <span className="font-medium text-foreground">{t("channels.proto.connect.share.lead")}</span> {t("channels.proto.connect.share.body")}{" "}
                  <button
                    type="button"
                    onClick={() => go("link")}
                    className="cursor-pointer rounded-sm font-medium text-primary-text underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {t("channels.proto.connect.share")}
                  </button>
                </p>
              </div>
              <DialogFooter className="-mx-6 -mb-6 px-6 py-4 sm:items-center sm:justify-between">
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <ExternalLink aria-hidden="true" className="size-3" />
                  {t("channels.proto.connect.opens")}
                </p>
                <div className="flex flex-wrap justify-end gap-2">
                  <Button variant="ghost" onClick={() => go(null)}>
                    {t("common.cancel")}
                  </Button>
                  <Button
                    disabled={!available(mode)}
                    onClick={() => {
                      go(null);
                      void start(mode);
                    }}
                  >
                    {t("channels.proto.connect.go")}
                  </Button>
                </div>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* El velo de Meta (§10.2): mientras espera no se cierra (Meta sigue abierto); con un fallo, sí. */}
      <Dialog open={veil !== null} onOpenChange={(open) => !open && failure && showVeil(null)}>
        <DialogContent showCloseButton={false} className="justify-items-center gap-4 p-8 text-center sm:max-w-120" data-slot="meta-veil">
          {failure && failure.code !== "cancelled" ? (
            <CircleAlert aria-hidden="true" className="size-8 text-destructive" />
          ) : (
            <BrandLogo brand="whatsapp" size="xl" />
          )}
          <DialogHeader className="items-center">
            <DialogTitle className="text-xl leading-tight font-semibold text-balance">{veilTitle}</DialogTitle>
            <DialogDescription className="max-w-prose text-pretty">{veilBody}</DialogDescription>
          </DialogHeader>
          {failure && veil ? (
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="ghost" onClick={() => showVeil(null)}>
                {t("common.close")}
              </Button>
              <Button onClick={() => void start(veil.mode)}>{t("channels.proto.veil.retry")}</Button>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {offer ? (
        <CatalogPicker
          key={offer.channelId}
          refId={refId}
          channelId={offer.channelId}
          current={null}
          open
          onOpenChange={(open) => {
            if (open) return;
            const channelId = offer.channelId;
            setOffer(null);
            configure(channelId);
          }}
          offer
          preloaded={offer.list}
        />
      ) : null}
    </>
  );
}
