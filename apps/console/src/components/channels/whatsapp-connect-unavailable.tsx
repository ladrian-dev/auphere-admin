"use client";

import { MessageCircle } from "lucide-react";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";

/**
 * F2 staging: Connect WhatsApp is a disabled button. No href, no onClick,
 * no Embedded Signup, no Meta SDK.
 */
export function WhatsAppConnectUnavailable({ used }: { used: number }) {
  const t = useT();
  const reasonId = "ch-connect-reason";
  return (
    <div className="flex max-w-sm flex-col items-end gap-1">
      <Button type="button" disabled aria-describedby={reasonId}>
        <MessageCircle aria-hidden="true" />
        {used > 0 ? t("ch.connect.another") : t("ch.connect")}
      </Button>
      <p id={reasonId} className="text-xs text-muted-foreground text-pretty">
        {t("ch.connect.unavailable")}
      </p>
    </div>
  );
}
