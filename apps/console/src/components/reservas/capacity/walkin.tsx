"use client";

import * as React from "react";

import { Button, Dialog, DialogContent, DialogHeader, DialogTitle, Field, Input, Skeleton } from "@nexus/ui";

import { addWaitlistAction, capacitySlotsAction, walkinAction } from "@/app/(console)/reservas/actions";
import type { CapacitySlots } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { fromMinutes, toMinutes } from "../model/dates";
import { useIdempotencyKey } from "../model/idempotency";
import { useActionLoad } from "../model/use-load";
import { currentSlotTime, nextSlotTime } from "../model/occupancy";
import { Stepper, useWrite } from "../shared";

export type WalkinVerdict =
  | { kind: "closed"; next: string | null }
  | { kind: "fits"; time: string; present: number; leftAfter: number; until: string }
  | { kind: "full"; time: string; present: number; firstFit: string | null };

/**
 * Whether a walk-in of `people` fits now (pure, so the three sentences are
 * testable). Walk-ins use the whole capacity in the slot in course (spec
 * Requisito 4.3): the slot's `left` is already counted that way when asked
 * with `walkin=true`.
 */
export function walkinVerdict(slots: CapacitySlots, people: number, nowMinutes: number, step: number, stay: number, seats: number): WalkinVerdict {
  const times = slots.slots.map((s) => s.time);
  const current = currentSlotTime(times, nowMinutes, step);
  if (!current || slots.closed) return { kind: "closed", next: slots.closed ? null : nextSlotTime(times, nowMinutes) };
  const slot = slots.slots.find((s) => s.time === current)!;
  const present = Math.max(0, seats - slot.left);
  const fits = slot.fits || (slot.why === "past" && slot.left >= people);
  if (fits) return { kind: "fits", time: current, present, leftAfter: Math.max(0, slot.left - people), until: fromMinutes(toMinutes(current) + stay) };
  return { kind: "full", time: current, present, firstFit: slots.first_fit };
}

/**
 * «Llega alguien sin reserva» (spec 043, T024): −/+ people, an optional name,
 * and the answer of the API for the slot in course — «Registrar llegada» if
 * it fits, «Apuntar en lista de espera» for the first slot that does if not,
 * or when the next service starts.
 */
export function WalkinBox({ onDone, bare = false }: { onDone?: () => void; bare?: boolean }) {
  const { t, today, nowMinutes, settings } = useReservas();
  const words = useWords();
  const write = useWrite();
  const key = useIdempotencyKey();
  const cap = settings.capacity;
  const [people, setPeople] = React.useState(2);
  const [name, setName] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [nameError, setNameError] = React.useState(false);
  const [reload, setReload] = React.useState(0);

  const check = useActionLoad(`${today}|${people}|${reload}`, () => capacitySlotsAction({ date: today, party_size: people, walkin: true }), {
    delayMs: 250,
  });

  const verdict =
    check.kind === "ok" && cap
      ? walkinVerdict(check.data, people, nowMinutes, cap.schedule.step_minutes, cap.stay_minutes, cap.seats)
      : null;

  async function register() {
    setBusy(true);
    const payload = { party_size: people, name: name.trim() || null };
    const res = await write(() => walkinAction({ ...payload, idempotencyKey: key.take(payload) }), { success: t("reservas.walkin.done") });
    setBusy(false);
    if (res.ok) {
      key.done();
      setName("");
      onDone?.();
    } else if (res.status === 409) setReload((n) => n + 1);
  }

  async function waitlist(time: string) {
    if (!name.trim()) {
      setNameError(true);
      return;
    }
    setBusy(true);
    const payload = { name: name.trim(), phone: null, party_size: people, date: today, time, in_person: true };
    const res = await write(() => addWaitlistAction({ ...payload, idempotencyKey: key.take(payload) }), {
      success: t("reservas.walkin.waitlisted", { time }),
    });
    setBusy(false);
    if (res.ok) {
      key.done();
      setName("");
      onDone?.();
    }
  }

  const body = (
    <div className="flex min-w-0 flex-col gap-3">
      {verdict && verdict.kind !== "closed" && cap ? (
        <p className="text-xs text-muted-foreground">
          {t("reservas.walkin.context", { time: verdict.time, present: verdict.present, seats: cap.seats })}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm">{t("reservas.walkin.people")}</span>
        <Stepper label={t("reservas.walkin.people")} value={people} onChange={setPeople} min={1} max={cap?.seats} />
      </div>
      <Field
        label={t("reservas.walkin.name")}
        optionalLabel={t("reservas.optional")}
        error={nameError && !name.trim() ? t("reservas.form.nameRequired") : null}
      >
        {(a11y) => <Input {...a11y} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoComplete="off" />}
      </Field>
      <div aria-live="polite" className="min-h-10 text-sm text-pretty">
        {check.kind === "loading" ? (
          <div role="status" aria-label={t("reservas.walkin.checking")}>
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : check.kind === "error" ? (
          <span role="alert" className="flex flex-wrap items-center gap-2 text-destructive">
            {t("common.error.backend")}
            <Button size="xs" variant="outline" onClick={() => setReload((n) => n + 1)}>
              {t("common.retry")}
            </Button>
          </span>
        ) : verdict?.kind === "fits" ? (
          t("reservas.walkin.fits", { left: verdict.leftAfter, until: verdict.until })
        ) : verdict?.kind === "full" ? (
          verdict.firstFit ? (
            t("reservas.walkin.noFit", { count: people, unit: words.unitFor(people), time: verdict.firstFit })
          ) : (
            t("reservas.walkin.noFitToday", { count: people, unit: words.unitFor(people) })
          )
        ) : verdict?.kind === "closed" ? (
          verdict.next ? (
            t("reservas.walkin.closed", { time: verdict.next })
          ) : (
            t("reservas.walkin.closedToday")
          )
        ) : null}
      </div>
      {verdict?.kind === "full" && verdict.firstFit && settings.waitlist.enabled ? (
        <Button onClick={() => void waitlist(verdict.firstFit!)} loading={busy}>
          {t("reservas.walkin.waitlist")}
        </Button>
      ) : (
        <Button onClick={() => void register()} loading={busy} disabled={verdict?.kind !== "fits"}>
          {t("reservas.walkin.register")}
        </Button>
      )}
    </div>
  );

  if (bare) return body;
  return (
    <section className="flex flex-col gap-3 rounded-md border border-border bg-card p-4">
      <h3 className="text-sm font-medium">{t("reservas.walkin.title")}</h3>
      {body}
    </section>
  );
}

/** The same box from the header's «Llegada sin reserva». */
export function WalkinDialog({ onClose }: { onClose: () => void }) {
  const { t } = useReservas();
  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("reservas.walkin.title")}</DialogTitle>
        </DialogHeader>
        <WalkinBox bare onDone={onClose} />
      </DialogContent>
    </Dialog>
  );
}
