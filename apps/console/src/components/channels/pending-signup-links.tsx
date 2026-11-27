"use client";

/**
 * The client's links that still work (owner, 2026-10-20), one per channel
 * since spec 085: each line says its channel.
 *
 * Before, every «Enviar enlace al cliente» left another valid link around and
 * the console could neither see nor revoke any of them. Now a new link
 * replaces the earlier one, and this line says which one is out there, until
 * when, and lets the partner revoke it. The link itself is never shown again:
 * Auphere only keeps its fingerprint.
 */

import { Link2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, formatDateTime } from "@nexus/ui";

import { revokeWhatsappSignupLinkAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useLocale, useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { SignupLinkRow } from "@/lib/backend/channels";

/** Brand names: the same in every language. */
const CHANNEL_NAME = { whatsapp: "WhatsApp", instagram: "Instagram", messenger: "Messenger" } as const;

export function PendingSignupLinks({
  refId,
  links,
  manage,
}: {
  refId: string;
  links: SignupLinkRow[];
  manage: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const [pending, start] = React.useTransition();
  const [confirm, setConfirm] = React.useState<string | null>(null);
  const live = links.filter((l) => l.state === "valid");
  if (live.length === 0) return null;
  const confirming = live.find((l) => l.id === confirm);
  const confirmingChannel = confirming?.channel ?? "whatsapp";

  function revoke(id: string) {
    start(async () => {
      const res = await revokeWhatsappSignupLinkAction({ ref: refId, id });
      setConfirm(null);
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      toast.success(t("ch.link.revoked"));
    });
  }

  return (
    <section aria-label={t("ch.link.pending.title")} className="flex flex-col gap-2">
      {live.map((l) => (
        <div
          key={l.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-md px-3 py-2 text-sm ring-1 ring-foreground/10"
        >
          <span className="flex min-w-0 items-center gap-2">
            <Link2 className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span>
              {(l.channel ?? "whatsapp") === "whatsapp"
                ? t("ch.link.pending.line", {
                    channel: CHANNEL_NAME.whatsapp,
                    mode: t(`ch.connect.mode.${l.mode as "coexistence" | "cloud_api" | "whatsapp_login"}`),
                    date: formatDateTime(l.expires_at, locale),
                  })
                : t("ch.link.pending.line.social", {
                    channel: CHANNEL_NAME[l.channel ?? "whatsapp"],
                    date: formatDateTime(l.expires_at, locale),
                  })}
            </span>
          </span>
          {manage ? (
            <Button variant="outline" size="sm" disabled={pending} onClick={() => setConfirm(l.id)}>
              {t("ch.link.revoke")}
            </Button>
          ) : null}
        </div>
      ))}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={t("ch.link.revoke.title")}
        description={
          confirmingChannel === "whatsapp" ? t("ch.link.revoke.body") : t("ch.link.revoke.body.social", { channel: CHANNEL_NAME[confirmingChannel] })
        }
        confirmLabel={t("ch.link.revoke")}
        destructive
        onConfirm={() => {
          if (confirm) revoke(confirm);
        }}
      />
    </section>
  );
}
