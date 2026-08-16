"use client";

import { MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Label } from "@nexus/ui";

import { whatsappSignupAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import { SignupError, loginWithMeta, type SignupMode } from "@/lib/meta-fb-sdk";

/** Meta Embedded Signup config handed down by the server component (env). */
export type MetaSignupConfig = {
  appId: string | null;
  graphVersion: string;
  configIdCloudApi: string | null;
  configIdCoexistence: string | null;
};

export const SELECT_CLASS =
  "h-8 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

/**
 * "Connect WhatsApp" — opens Meta's popup (FB.login with our config id),
 * waits for code + WABA ids, posts them to the console API. Disabled with
 * the reason when the client's channel quota is full or when the
 * environment has no Meta app configured.
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
  const [mode, setMode] = React.useState<SignupMode>("cloud_api");
  const [working, setWorking] = React.useState(false);
  const configured = !!meta.appId && !!(meta.configIdCloudApi || meta.configIdCoexistence);
  const configId = mode === "coexistence" ? meta.configIdCoexistence : meta.configIdCloudApi;
  const disabledReason = !canConnect ? t("ch.quota.full", { used, max }) : !configured ? t("ch.connect.notConfigured") : null;

  async function start() {
    if (!meta.appId || !configId) return;
    setWorking(true);
    try {
      const envelope = await loginWithMeta({ appId: meta.appId, version: meta.graphVersion, configId, mode });
      const res = await whatsappSignupAction({ ref: refId, mode, ...envelope });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("ch.connect.done", { phone: res.data.display_phone_number }));
      setOpen(false);
      router.refresh();
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
      <Dialog open={open} onOpenChange={(o) => !working && setOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("ch.connect")}</DialogTitle>
            <DialogDescription>{t("ch.connect.help")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="ch-mode">{t("ch.connect.mode")}</Label>
            <select id="ch-mode" className={SELECT_CLASS} value={mode} onChange={(e) => setMode(e.target.value as SignupMode)} disabled={working}>
              {meta.configIdCloudApi ? <option value="cloud_api">{t("ch.connect.mode.cloud_api")}</option> : null}
              {meta.configIdCoexistence ? <option value="coexistence">{t("ch.connect.mode.coexistence")}</option> : null}
            </select>
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
