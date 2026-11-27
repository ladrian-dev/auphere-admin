"use client";

import { CheckCircle2 } from "lucide-react";
import * as React from "react";

import { Button, EmptyState } from "@nexus/ui";

import { useMetaSocialConnect, type MetaSocialConnectActions } from "@/components/channels/meta-social-connect";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ActionResult } from "@/lib/actions";
import type { MetaSocialConnectResult, MetaSocialKind, MetaSocialOffer } from "@/lib/backend/channels";

import { ownerSocialCompleteAction, ownerSocialConnectAction } from "./actions";

/** The link stopped working while the page was open: the WhatsApp page's words (5.6). */
const DEAD = {
  link_used: "used",
  link_expired: "expired",
  link_revoked: "revoked",
  link_unknown: "unknown",
} as const;
type Dead = (typeof DEAD)[keyof typeof DEAD];

/**
 * Spec 085: the page the business owner opens from an Instagram or Messenger
 * link. It is the console's own connection (`useMetaSocialConnect`, specs 049
 * and 081) with the link's actions: the same «¿Cómo entras a Meta?», the same
 * window, the same account picker and the same refusals. The token never
 * reaches this page: the actions read it from the channel's cookie.
 */
export function OwnerConnectSocial({ kind, name, offer }: { kind: MetaSocialKind; name: string; offer: MetaSocialOffer }) {
  const t = useT();
  const [connected, setConnected] = React.useState<string | null>(null);
  const [dead, setDead] = React.useState<Dead | null>(null);

  const actions = React.useMemo<MetaSocialConnectActions>(() => {
    function watch(res: ActionResult<MetaSocialConnectResult>) {
      if (!res.ok && res.code && res.code in DEAD) setDead(DEAD[res.code as keyof typeof DEAD]);
      return res;
    }
    return {
      connect: async (k, code) => watch(await ownerSocialConnectAction({ kind: k, code })),
      complete: async (k, nonce, accountId) => watch(await ownerSocialCompleteAction({ kind: k, nonce, accountId })),
    };
  }, []);

  const social = useMetaSocialConnect({
    offer,
    actions,
    failureHint: "connect.social.tell",
    onDone: (res) => setConnected(res.display_name ?? ""),
  });

  if (dead) {
    return <EmptyState title={t(`connect.dead.${dead}`)} description={t("connect.dead.body")} readonly />;
  }

  if (connected !== null) {
    return (
      <section className="flex flex-col gap-4" aria-live="polite">
        <CheckCircle2 className="size-10 text-status-positive-text" aria-hidden="true" />
        <h1 className="text-2xl font-semibold text-balance">{t(`connect.social.done.${kind}` as MessageKey)}</h1>
        <p className="text-sm text-pretty text-muted-foreground">{t("connect.social.done.body", { name: connected })}</p>
      </section>
    );
  }

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex min-w-0 flex-col gap-2">
        <h1 className="text-2xl font-semibold text-balance">{t(`connect.social.title.${kind}` as MessageKey, { name })}</h1>
        <p className="text-sm text-pretty text-muted-foreground">{t(`connect.social.body.${kind}` as MessageKey)}</p>
      </div>
      <Button size="lg" onClick={() => void social.start(kind)} disabled={social.working} aria-busy={social.working}>
        {social.working ? t("connect.working") : t(`connect.social.start.${kind}` as MessageKey)}
      </Button>
      {social.dialog}
    </section>
  );
}
