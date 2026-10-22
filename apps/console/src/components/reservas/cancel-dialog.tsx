"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Checkbox, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Label, Skeleton, cn } from "@nexus/ui";

import { cancelBookingAction, cancelPreviewAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { Booking, CancelPreview } from "@/lib/backend/reservas";

import { useReservas, useWords } from "./context";
import { formatMinutes } from "./model/dates";
import { failureMessage, firstName } from "./model/vocab";

type Preview = { kind: "loading" } | { kind: "none" } | { kind: "ok"; data: CancelPreview };

/**
 * «Cancelar la reserva» (spec 043, T023). «Avisar a Ana por WhatsApp» when
 * there is a phone. In Servicios the preview says whether the slot can go to
 * the waitlist — «¿Quieres que el agente intente llenar el hueco?» with how
 * many fit — or why not (list off, too soon for the lead, nobody fits).
 */
export function CancelDialog({ booking: b, onClose }: { booking: Booking; onClose: () => void }) {
  const { t, mode, settings, refresh } = useReservas();
  const words = useWords();
  const [notify, setNotify] = React.useState(true);
  const [offer, setOffer] = React.useState<"yes" | "no">("yes");
  const [preview, setPreview] = React.useState<Preview>(mode === "services" ? { kind: "loading" } : { kind: "none" });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const name = b.contact.name ?? t("reservas.detail.walkinName");

  React.useEffect(() => {
    if (mode !== "services") return;
    let live = true;
    cancelPreviewAction({ id: b.id })
      .then((res) => live && setPreview(res.ok ? { kind: "ok", data: res.data } : { kind: "none" }))
      .catch(() => live && setPreview({ kind: "none" }));
    return () => {
      live = false;
    };
  }, [b.id, mode]);

  const canOffer = preview.kind === "ok" && preview.data.can_offer && preview.data.candidates > 0;
  const why = preview.kind === "ok" && !canOffer ? preview.data.why_not : null;

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const res = await cancelBookingAction({
        id: b.id,
        version: b.version,
        notify: !!b.contact.phone && notify,
        offer_slot: canOffer && offer === "yes",
      });
      if (res.ok) {
        toast.success(
          res.data.offer ? t("reservas.cancel.done.offer", { count: res.data.offer.candidates }) : t("reservas.cancel.done"),
        );
        refresh();
        onClose();
        return;
      }
      const f = failureMessage(res);
      setError(t(f.key as MessageKey, f.vars));
      if (res.status === 412 || res.status === 409) refresh();
    } catch {
      setError(t("common.error.backend"));
    } finally {
      setBusy(false);
    }
  }

  const subtitle =
    mode === "services"
      ? t("reservas.cancel.subtitle.services", {
          name,
          service: b.service?.name ?? "",
          when: words.at(b.local.date, b.local.start),
          staff: b.staff?.name ?? "",
        })
      : t("reservas.cancel.subtitle.capacity", { name, people: words.people(b.party_size), when: words.at(b.local.date, b.local.start) });

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="sm:max-w-md" aria-busy={busy || undefined}>
        <DialogHeader>
          <DialogTitle>{t("reservas.cancel.title")}</DialogTitle>
          <DialogDescription>{subtitle}</DialogDescription>
        </DialogHeader>

        {b.contact.phone ? (
          <div className="flex items-center gap-3">
            <Checkbox id="reservas-cancel-notify" checked={notify} onCheckedChange={(v) => setNotify(v === true)} />
            <Label htmlFor="reservas-cancel-notify">{t("reservas.cancel.notify", { name: firstName(name) })}</Label>
          </div>
        ) : null}

        {preview.kind === "loading" ? (
          <div role="status" aria-label={t("reservas.cancel.preview.loading")} className="grid gap-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : canOffer && preview.kind === "ok" ? (
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium">{t("reservas.cancel.offer.question")}</legend>
            <OfferOption
              checked={offer === "yes"}
              onSelect={() => setOffer("yes")}
              label={t("reservas.cancel.offer.yes")}
              hint={
                preview.data.candidates === 1
                  ? t("reservas.cancel.offer.yesHint.one")
                  : t("reservas.cancel.offer.yesHint.other", { count: preview.data.candidates })
              }
            />
            <OfferOption checked={offer === "no"} onSelect={() => setOffer("no")} label={t("reservas.cancel.offer.no")} />
          </fieldset>
        ) : why && why !== "not_services" ? (
          <p role="note" className="rounded-md bg-muted px-3 py-2 text-sm text-pretty text-muted-foreground">
            {t(`reservas.cancel.why.${why}` as MessageKey, { lead: formatMinutes(settings.waitlist.lead_minutes) })}
          </p>
        ) : null}

        {error ? (
          <p role="alert" className="text-sm text-destructive text-pretty">
            {error}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy} autoFocus>
            {t("reservas.cancel.back")}
          </Button>
          <Button variant="destructive" onClick={() => void confirm()} loading={busy} disabled={preview.kind === "loading"}>
            {t("reservas.cancel.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OfferOption({ checked, onSelect, label, hint }: { checked: boolean; onSelect: () => void; label: string; hint?: string }) {
  const id = React.useId();
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 text-sm transition-colors duration-(--duration-hover)",
        checked ? "border-primary bg-primary/10" : "border-border hover:bg-muted",
      )}
    >
      <input id={id} type="radio" name="reservas-offer" checked={checked} onChange={onSelect} className="mt-1 size-4 accent-primary" />
      <span className="grid gap-1">
        <span className="font-medium">{label}</span>
        {hint ? <span className="text-xs text-muted-foreground text-pretty">{hint}</span> : null}
      </span>
    </label>
  );
}
