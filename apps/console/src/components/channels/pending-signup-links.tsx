"use client";

/**
 * The client's WhatsApp link that still works (owner, 2026-10-20).
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
              {t("ch.link.pending.line", {
                mode: t(`ch.connect.mode.${l.mode}`),
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
        description={t("ch.link.revoke.body")}
        confirmLabel={t("ch.link.revoke")}
        destructive
        onConfirm={() => {
          if (confirm) revoke(confirm);
        }}
      />
    </section>
  );
}
