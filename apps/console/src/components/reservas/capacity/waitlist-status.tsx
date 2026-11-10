"use client";

import { Button, StatusBadge } from "@nexus/ui";

import type { WaitlistEntry } from "@/lib/backend/reservas";

import { useReservas } from "../context";
import { canOffer, minutesLeft } from "../model/waitlist";

/**
 * Where an Aforo waitlist entry stands (design: Cabe / No cabe / Ofrecida ·
 * N min / Aceptó · reservada), with «Ofrecer» only when it can be offered:
 * waiting, fits now, no offer open.
 */
export function WaitlistStatus({ entry: w, onOffer }: { entry: WaitlistEntry; onOffer: () => void }) {
  const { t, now } = useReservas();
  if (w.status === "accepted") return <StatusBadge tone="positive">{t("reservas.wl.status.accepted")}</StatusBadge>;
  if (w.offer) {
    return <StatusBadge tone="info">{t("reservas.wl.status.offered", { minutes: minutesLeft(w.offer.deadline_at, now) })}</StatusBadge>;
  }
  if (canOffer(w)) {
    return (
      <span className="inline-flex items-center gap-2">
        <StatusBadge tone="positive">{t("reservas.wl.status.fits")}</StatusBadge>
        <Button size="xs" variant="outline" aria-label={t("reservas.wl.offer.aria", { name: w.contact.name ?? "" })} onClick={onOffer}>
          {t("reservas.wl.offer")}
        </Button>
      </span>
    );
  }
  if (w.fits_now === false) return <StatusBadge tone="muted">{t("reservas.wl.status.noFit")}</StatusBadge>;
  return <StatusBadge tone="muted">{t("reservas.wl.status.waiting")}</StatusBadge>;
}
