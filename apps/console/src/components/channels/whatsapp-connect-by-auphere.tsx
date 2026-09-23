"use client";

import { MessageCircle } from "lucide-react";

import { useT } from "@/i18n/client";

/**
 * Spec 016 (R1.3): the environment has no Meta app configured, so there is
 * no button — a disabled one would promise something that cannot happen
 * here (§V). The note says who connects the number and what to send.
 */
export function WhatsAppConnectByAuphere() {
  const t = useT();
  return (
    <div className="flex max-w-sm flex-col gap-1 rounded-md border border-border px-3 py-2" role="status">
      <p className="flex items-center gap-2 text-sm font-medium">
        <MessageCircle aria-hidden="true" className="size-4" />
        {t("ch.connect.byAuphere.title")}
      </p>
      <p className="text-xs text-muted-foreground text-pretty">{t("ch.connect.byAuphere.body")}</p>
      <p className="text-xs text-muted-foreground text-pretty">{t("ch.connect.byAuphere.contact")}</p>
    </div>
  );
}
