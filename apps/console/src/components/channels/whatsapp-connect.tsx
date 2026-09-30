"use client";

import { MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Label, NativeSelect } from "@nexus/ui";

import { listCatalogsAction, whatsappSignupAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { CatalogList } from "@/lib/backend/channels";
import { actionErrorText } from "@/lib/action-error";
import { SignupError, loginWithMeta, type SignupMode } from "@/lib/meta-fb-sdk";

import { CatalogPicker, offerCatalogAfterSignup } from "./catalog-picker";

/** Meta Embedded Signup config handed down by the server component (env). */
export type MetaSignupConfig = {
  appId: string | null;
  graphVersion: string;
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
export function MetaWindowVeil({ open }: { open: boolean }) {
  const t = useT();
  if (!open) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-slot="meta-window-veil"
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-2 bg-dark-green/95 px-6 text-center text-pistachio"
    >
      <p className="text-lg font-medium">{t("ch.connect.veil.title")}</p>
      <p className="max-w-md text-sm text-pistachio/80">{t("ch.connect.veil.body")}</p>
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
  // Historia 2 (spec 022): al terminar el alta, si el negocio tiene catálogo,
  // se ofrece aquí mismo; se puede saltar, y la tarjeta lo vuelve a ofrecer.
  const [offer, setOffer] = React.useState<{ channelId: string; list: CatalogList } | null>(null);
  const configId = mode === "coexistence" ? meta.configIdCoexistence : meta.configIdCloudApi;
  const disabledReason = !canConnect ? t("ch.quota.full", { used, max }) : null;

  async function start() {
    if (!meta.appId || !configId) return;
    setWorking(true);
    try {
      const envelope = await loginWithMeta({ appId: meta.appId, version: meta.graphVersion, configId, mode });
      const res = await whatsappSignupAction({ ref: refId, mode, ...envelope });
      if (!res.ok) {
        // R1.4 / R4.2: the number is someone else's, or its previous owner
        // still holds it at Meta — say so, not «error».
        const key = signupFailureKey(res.code);
        return void toast.error(key ? t(key) : actionErrorText(res, t));
      }
      // R1.2: the card, the list and the onboarding are recomputed on the
      // server; the toast says what changed for the client right now.
      toast.success(
        res.data.client_status === "active" ? t("ch.connect.done.active", { phone: res.data.display_phone_number }) : t("ch.connect.done", { phone: res.data.display_phone_number }),
      );
      setOpen(false);
      router.refresh();
      const list = await listCatalogsAction({ ref: refId, channelId: res.data.channel_id });
      if (offerCatalogAfterSignup(list) && list.ok) setOffer({ channelId: res.data.channel_id, list: list.data });
    } catch (err) {
      const code = err instanceof SignupError ? err.code : "meta_error";
      const key = (
        { sdk_failed: "ch.connect.sdkFailed", cancelled: "ch.connect.cancelled", timeout: "ch.connect.timeout", no_code: "ch.connect.noCode", meta_error: "common.error.backend" } as const
      )[code];
      toast.error(t(key));
    } finally {
      setWorking(false);
    }
  }

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
      <MetaWindowVeil open={working} />
      {offer ? (
        <CatalogPicker
          key={offer.channelId}
          refId={refId}
          channelId={offer.channelId}
          current={null}
          open
          onOpenChange={(o) => !o && setOffer(null)}
          offer
          preloaded={offer.list}
        />
      ) : null}
      <Dialog open={open} onOpenChange={(o) => !working && setOpen(o)}>
        <DialogContent>
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
