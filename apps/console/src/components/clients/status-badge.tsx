import { StatusBadge, type DotTone } from "@nexus/ui";

import type { Locale } from "@/i18n/messages";
import { statusKey, t } from "@/i18n/messages";

const TONE: Record<string, DotTone> = {
  active: "positive",
  provisioning: "info",
  paused: "warning",
  archived: "muted",
  staged: "info",
  suspended: "warning",
  pending: "info",
  open: "info",
  closed: "muted",
  escalated: "warning",
  connected: "positive",
  disconnected: "danger",
  degraded: "warning",
};

export function ClientStatusBadge({ status, locale }: { status: string; locale: Locale }) {
  return (
    // Sin latido: parpadear es el gesto de «espera, esto está pasando». Un
    // cliente sin activar no espera a nada — espera a que alguien lo active.
    <StatusBadge tone={TONE[status] ?? "muted"}>
      {t(locale, statusKey(status))}
    </StatusBadge>
  );
}
