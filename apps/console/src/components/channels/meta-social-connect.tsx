"use client";

import { AtSign, CircleAlert, MessagesSquare } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@nexus/ui";

import { metaSocialCompleteAction, metaSocialConnectAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { MetaSocialAccount, MetaSocialConnectResult, MetaSocialKind, MetaSocialOffer } from "@/lib/backend/channels";
import { SignupError, loginForCode, type SignupErrorCode } from "@/lib/meta-fb-sdk";

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

/** Spec 081: how the business signs in — `page` is Instagram with its
 *  linked Facebook Page (Facebook only); `default` is the channel's usual
 *  configuration. */
type Via = "default" | "page";

const LOGIN_ERRORS = {
  sdk_failed: "ch.connect.sdkFailed",
  cancelled: "ch.connect.cancelled",
  timeout: "ch.connect.timeout",
  no_code: "ch.connect.noCode",
  meta_error: "common.error.backend",
  no_number: "ch.connect.noNumber",
  grant_only: "ch.connect.grantOnly",
} as const satisfies Record<SignupErrorCode, MessageKey>;

/**
 * Spec 049 — the Instagram / Messenger connection, as a hook: opens Facebook
 * Login for Business with the channel's configuration, hands the single-use
 * code to the server and, when the business granted several accounts or
 * Pages, asks which one (`dialog`). The old Channels page wraps it in a
 * button; the new console's channel wizard calls `start` from its card.
 */
export function useMetaSocialConnect({
  refId,
  offer,
  onConnected,
}: {
  refId: string;
  offer: MetaSocialOffer | null;
  onConnected?: (res: MetaSocialConnectResult) => void | Promise<void>;
}) {
  const t = useT();
  const router = useRouter();
  const [working, setWorking] = React.useState(false);
  const [choice, setChoice] = React.useState<{ kind: MetaSocialKind; via: Via; nonce: string; accounts: MetaSocialAccount[] } | null>(null);
  // A failure stays on screen with «Intentar de nuevo», as WhatsApp's veil
  // does, instead of a toast that goes away (QA 2026-10-30). It keeps the way
  // in, so the retry opens the same window (spec 081, 1.6).
  const [failure, setFailure] = React.useState<{ kind: MetaSocialKind; via: Via; key: MessageKey } | null>(null);
  // Spec 081, 1.2: Instagram with both configurations asks how to sign in.
  const [asking, setAsking] = React.useState(false);
  // Spec 049, 7.2: mientras la ventana de Meta está abierta se puede cancelar.
  // Cada intento lleva su número: lo que Meta devuelva a un intento cancelado
  // se descarta, sin conectar nada.
  const [waitingMeta, setWaitingMeta] = React.useState(false);
  const attempt = React.useRef(0);

  async function done(res: MetaSocialConnectResult) {
    const name = res.channel?.username ? `@${res.channel.username}` : (res.channel?.display_name ?? "");
    setChoice(null);
    await onConnected?.(res);
    toast.success(t("ch.social.done", { name }));
    router.refresh();
  }

  function refused(kind: MetaSocialKind, via: Via, code: string | null | undefined) {
    const key = code ? META_SOCIAL_REASONS[code] : undefined;
    setFailure({ kind, via, key: key ?? "common.error.backend" });
  }

  async function start(kind: MetaSocialKind) {
    const entry = offer?.channels.find((c) => c.kind === kind);
    if (!offer || !entry) return;
    if (kind === "instagram" && entry.page_config_id) {
      setFailure(null);
      setAsking(true);
      return;
    }
    await open(kind, "default");
  }

  async function open(kind: MetaSocialKind, via: Via) {
    const entry = offer?.channels.find((c) => c.kind === kind);
    // Spec 081, 1.3: with the Page, the Facebook-only configuration.
    const configId = via === "page" ? entry?.page_config_id : entry?.config_id;
    if (!offer || !configId) return;
    setAsking(false);
    const mine = ++attempt.current;
    setFailure(null);
    setWorking(true);
    setWaitingMeta(true);
    try {
      // Spec 049, R8: Instagram's configuration lets the business sign in
      // with Instagram too; `prompt` keeps an open Facebook session from
      // skipping that choice. Messenger, and Instagram with its Page (spec
      // 081), only sign in with Facebook.
      const prompt = kind === "instagram" && via !== "page" ? { prompt: "login" as const } : {};
      const code = await loginForCode({ appId: offer.app_id, version: offer.graph_version, configId, ...prompt });
      if (attempt.current !== mine) return;
      setWaitingMeta(false);
      const res = await metaSocialConnectAction({ ref: refId, kind, code });
      if (!res.ok) return void refused(kind, via, res.code);
      if (res.data.status === "choose" && res.data.nonce) {
        setChoice({ kind, via, nonce: res.data.nonce, accounts: res.data.accounts });
        return;
      }
      await done(res.data);
    } catch (err) {
      if (attempt.current !== mine) return;
      setFailure({ kind, via, key: LOGIN_ERRORS[err instanceof SignupError ? err.code : "meta_error"] });
    } finally {
      if (attempt.current === mine) {
        setWorking(false);
        setWaitingMeta(false);
      }
    }
  }

  const cancelWait = React.useCallback(() => {
    attempt.current += 1;
    setWorking(false);
    setWaitingMeta(false);
  }, []);

  async function pick(account: MetaSocialAccount) {
    if (!choice) return;
    setWorking(true);
    try {
      const res = await metaSocialCompleteAction({ ref: refId, kind: choice.kind, nonce: choice.nonce, accountId: account.id });
      if (!res.ok) {
        const { kind, via } = choice;
        setChoice(null);
        return void refused(kind, via, res.code);
      }
      await done(res.data);
    } finally {
      setWorking(false);
    }
  }

  const dialog = (
    <>
      <MetaWindowVeil open={working && !choice} note="ch.social.veil.access" onCancel={waitingMeta ? cancelWait : undefined} />
      <Dialog open={failure !== null} onOpenChange={(o) => !o && setFailure(null)}>
        <DialogContent showCloseButton={false} className="justify-items-center gap-4 p-8 text-center sm:max-w-120" data-slot="meta-social-failure">
          <CircleAlert aria-hidden="true" className="size-8 text-destructive" />
          <DialogHeader className="items-center">
            <DialogTitle className="text-xl leading-tight font-semibold text-balance">{t("channels.proto.veil.failed")}</DialogTitle>
            <DialogDescription className="max-w-prose text-pretty">{failure ? t(failure.key) : null}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap justify-center gap-2">
            <Button variant="ghost" onClick={() => setFailure(null)}>
              {t("common.close")}
            </Button>
            <Button onClick={() => failure && void open(failure.kind, failure.via)}>{t("channels.proto.veil.retry")}</Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={asking} onOpenChange={(o) => !o && setAsking(false)}>
        <DialogContent data-slot="meta-social-how">
          <DialogHeader>
            <DialogTitle>{t("ch.social.how.title")}</DialogTitle>
            <DialogDescription className="text-pretty">{t("ch.social.how.body")}</DialogDescription>
          </DialogHeader>
          <ul className="flex flex-col gap-2">
            {(
              [
                ["page", "ch.social.how.page", "ch.social.how.page.help"],
                ["default", "ch.social.how.instagram", "ch.social.how.instagram.help"],
              ] as const
            ).map(([via, title, help]) => (
              <li key={via}>
                <Button
                  variant="outline"
                  className="h-auto w-full min-w-0 flex-col items-start gap-1 py-3 text-left whitespace-normal"
                  onClick={() => void open("instagram", via)}
                >
                  <span className="font-medium">{t(title)}</span>
                  <span className="text-xs font-normal text-pretty text-muted-foreground">{t(help)}</span>
                </Button>
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAsking(false)}>
              {t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={choice !== null}
        onOpenChange={(o) => {
          if (o || working) return;
          setChoice(null);
          toast.info(t("ch.social.choose.cancelled"));
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t(choice?.kind === "messenger" ? "ch.social.choose.messenger" : "ch.social.choose.instagram")}</DialogTitle>
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
          <DialogFooter>
            <Button
              variant="outline"
              disabled={working}
              onClick={() => {
                setChoice(null);
                toast.info(t("ch.social.choose.cancelled"));
              }}
            >
              {t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
  return { start, working, dialog };
}

/**
 * «Conectar Instagram» / «Conectar Messenger» on the Channels page. The page
 * renders it only for the channels the partner has (``overview.meta_social``):
 * absent otherwise (§V).
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
  const { start, working, dialog } = useMetaSocialConnect({ refId, offer });
  if (!offer.channels.some((c) => c.kind === kind)) return null;
  const Icon = kind === "instagram" ? AtSign : MessagesSquare;
  return (
    <>
      <Button variant={variant} onClick={() => void start(kind)} disabled={working} aria-busy={working}>
        <Icon aria-hidden="true" />
        {t(kind === "instagram" ? "ch.social.connect.instagram" : "ch.social.connect.messenger")}
      </Button>
      {dialog}
    </>
  );
}
