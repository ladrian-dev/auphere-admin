import type { LocalSpan, SlotOffer, WaitlistEntry } from "@/lib/backend/reservas";

/**
 * The waitlist and its offers (spec 043, Historia 6). An offer writes to one
 * person at a time (Servicios, 5 min each, up to 5) or opens one per hour
 * (Aforo, 15 min). The card says who has the turn and how long is left.
 */

export type OfferState =
  | { kind: "running"; current: SlotOffer["candidates"][number] | null; index: number; total: number }
  | { kind: "filled" }
  | { kind: "stopped" }
  | { kind: "nobody" };

export function offerState(offer: SlotOffer): OfferState {
  const candidates = [...offer.candidates].sort((a, b) => a.position - b.position);
  if (offer.filled_booking_id || candidates.some((c) => c.status === "accepted" || c.status === "late_won")) {
    return { kind: "filled" };
  }
  if (offer.status === "running") {
    const index = candidates.findIndex((c) => c.status === "waiting");
    return { kind: "running", current: index >= 0 ? candidates[index]! : null, index: index >= 0 ? index + 1 : 0, total: candidates.length };
  }
  if (candidates.some((c) => c.status === "stopped")) return { kind: "stopped" };
  return { kind: "nobody" };
}

/** «4:59» left until `deadline`, or `null` once it passed. */
export function countdown(deadline: string | null | undefined, now: Date): string | null {
  if (!deadline) return null;
  const left = Math.floor((new Date(deadline).getTime() - now.getTime()) / 1000);
  if (!Number.isFinite(left) || left <= 0) return null;
  return `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
}

/** Whole minutes left until `deadline` (at least 1 while it is open), for «Ofrecida · quedan 12 min». */
export function minutesLeft(deadline: string | null | undefined, now: Date): number {
  if (!deadline) return 0;
  const ms = new Date(deadline).getTime() - now.getTime();
  return ms > 0 ? Math.max(1, Math.ceil(ms / 60_000)) : 0;
}

/** An entry that is still in the list (the API may also send what was removed or expired). */
export function isListed(entry: Pick<WaitlistEntry, "status">): boolean {
  return entry.status !== "removed" && entry.status !== "expired";
}

/** «Ofrecer» only to someone waiting, who fits now, with no offer open. */
export function canOffer(entry: Pick<WaitlistEntry, "status" | "fits_now" | "offer">): boolean {
  return entry.status === "waiting" && entry.fits_now === true && entry.offer === null;
}

/** A slot held while it is offered to the waitlist: who has the turn, «i de n» (design §3.1). */
export type HeldSlot = { id: string; local: LocalSpan; index: number; total: number };

/**
 * The slots being offered right now to the waitlist, of one professional on
 * one day: the grid draws them dashed and nobody books on top of them. An
 * offer someone already took is a booking, not a held slot.
 */
export function heldSlots(offers: readonly SlotOffer[] | null | undefined, date: string, staffId: string | null): HeldSlot[] {
  return (offers ?? []).flatMap((o) => {
    if (o.slot.local.date !== date || (o.slot.staff?.id ?? null) !== staffId) return [];
    const state = offerState(o);
    return state.kind === "running" ? [{ id: o.id, local: o.slot.local, index: state.index, total: state.total }] : [];
  });
}
