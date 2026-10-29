"use client";

import { AtSign, MessagesSquare } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@nexus/ui";

import { metaSocialCompleteAction, metaSocialConnectAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { MetaSocialAccount, MetaSocialConnectResult, MetaSocialKind, MetaSocialOffer } from "@/lib/backend/channels";
import { SignupError, loginForCode } from "@/lib/meta-fb-sdk";

import { MetaWindowVeil } from "./whatsapp-connect";

/** The API's refusals, in words (principle III). Unknown codes fall back. */
export const META_SOCIAL_REASONS: Record<string, MessageKey> = {
  code_exchange_failed: "ch.social.reason.code_exchange_failed",
  no_business_portfolio: "ch.social.reason.no_business_portfolio",
  no_instagram_account: "ch.social.reason.no_instagram_account",
  no_page: "ch.social.reason.no_page",
  messages_disabled: "ch.social.reason.messages_disabled",
  missing_permission: "ch.social.reason.missing_permission",
  page_messaging_task_missing: "ch.social.reason.page_messaging_task_missing",
  already_connected_elsewhere: "ch.social.reason.already_connected_elsewhere",
  subscribe_failed: "ch.social.reason.subscribe_failed",
  pending_expired: "ch.social.reason.pending_expired",
};

const LOGIN_ERRORS = {
  sdk_failed: "ch.connect.sdkFailed",
  cancelled: "ch.connect.cancelled",
  timeout: "ch.connect.timeout",
  no_code: "ch.connect.noCode",
  meta_error: "common.error.backend",
} as const satisfies Record<string, MessageKey>;

/**
 * Spec 049 — «Conectar Instagram» / «Conectar Messenger». Opens Facebook
 * Login for Business with the channel's configuration, hands the single-use
 * code to the server and, when the business granted several accounts or
 * Pages, asks which one. The page renders it only for the channels the
 * partner has (``overview.meta_social``): absent otherwise (§V).
 */
export function MetaSocialConnect({
  refId,
  offer,
  kind,
  variant = "outline",
}: {
  refId: string;
  offer: MetaSocialOffer;
  kind: MetaSocialKind;
  variant?: "default" | "outline";
}) {
  const t = useT();
  const router = useRouter();
  const [working, setWorking] = React.useState(false);
  const [choice, setChoice] = React.useState<{ nonce: string; accounts: MetaSocialAccount[] } | null>(null);
  const configId = offer.channels.find((c) => c.kind === kind)?.config_id;

  function done(res: MetaSocialConnectResult) {
    const name = res.channel?.username ? `@${res.channel.username}` : (res.channel?.display_name ?? "");
    toast.success(t("ch.social.done", { name }));
    setChoice(null);
    router.refresh();
  }

  function refused(code: string | null | undefined) {
    const key = code ? META_SOCIAL_REASONS[code] : undefined;
    toast.error(t(key ?? "common.error.backend"));
  }

  async function start() {
    if (!configId) return;
    setWorking(true);
    try {
      const code = await loginForCode({ appId: offer.app_id, version: offer.graph_version, configId });
      const res = await metaSocialConnectAction({ ref: refId, kind, code });
      if (!res.ok) return void refused(res.code);
      if (res.data.status === "choose" && res.data.nonce) {
        setChoice({ nonce: res.data.nonce, accounts: res.data.accounts });
        return;
      }
      done(res.data);
    } catch (err) {
      toast.error(t(LOGIN_ERRORS[err instanceof SignupError ? err.code : "meta_error"]));
    } finally {
      setWorking(false);
    }
  }

  async function pick(account: MetaSocialAccount) {
    if (!choice) return;
    setWorking(true);
    try {
      const res = await metaSocialCompleteAction({ ref: refId, kind, nonce: choice.nonce, accountId: account.id });
      if (!res.ok) {
        setChoice(null);
        return void refused(res.code);
      }
      done(res.data);
    } finally {
      setWorking(false);
    }
  }

  if (!configId) return null;
  const Icon = kind === "instagram" ? AtSign : MessagesSquare;
  return (
    <>
      <Button variant={variant} onClick={start} disabled={working} aria-busy={working}>
        <Icon aria-hidden="true" />
        {t(kind === "instagram" ? "ch.social.connect.instagram" : "ch.social.connect.messenger")}
      </Button>
      <MetaWindowVeil open={working && !choice} />
      <Dialog open={choice !== null} onOpenChange={(o) => !o && !working && setChoice(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t(kind === "instagram" ? "ch.social.choose.instagram" : "ch.social.choose.messenger")}</DialogTitle>
            <DialogDescription>{t("ch.social.choose.body")}</DialogDescription>
          </DialogHeader>
          <ul className="flex flex-col gap-2">
            {(choice?.accounts ?? []).map((a) => (
              <li key={a.id}>
                <Button variant="outline" className="w-full justify-start" disabled={working} onClick={() => pick(a)}>
                  <span className="truncate">
                    {a.username ? `@${a.username}` : a.name}
                    {a.username && a.name !== a.username ? <span className="text-muted-foreground"> · {a.name}</span> : null}
                  </span>
                </Button>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
