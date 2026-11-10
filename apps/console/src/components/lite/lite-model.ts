import type { Locale } from "@/i18n/messages";
import type { LiteBalance } from "@/lib/backend/lite";

/**
 * The client console's pure rules (spec 045). No React, no requests: what
 * the Panel and the Consumo must not get wrong is pinned by a plain test.
 */

export type RunwayTone = "positive" | "warning" | "danger";
export type BalanceRunway = { days: number; monthLeft: number; tone: RunwayTone };

/** Under 7 days it alarms, under 14 it warns, otherwise it is the primary tone (R4.3). */
function toneFor(days: number): RunwayTone {
  if (days < 7) return "danger";
  if (days < 14) return "warning";
  return "positive";
}

/**
 * «Cubre N de M días del mes» (contract §3): M is the days left in the month
 * as the API counts them —today included, in the business's zone—, N the
 * whole days the balance lasts at the last 7 days' pace, never more than M.
 * A used-up balance is 0 of M in the alarm tone. No bar without a pace (no
 * spend), without an allocation, or without a month to divide by: the card
 * says it in words instead of drawing a number nobody measured.
 */
export function balanceRunway(balance: LiteBalance | null): BalanceRunway | null {
  if (!balance?.assigned || balance.remaining_cents == null) return null;
  const monthLeft = balance.month_days_left;
  if (!(monthLeft >= 1)) return null;
  if (balance.remaining_cents <= 0) return { days: 0, monthLeft, tone: "danger" };
  if (balance.days_left == null) return null;
  const lasts = Math.max(0, Math.floor(balance.days_left));
  return { days: Math.min(lasts, monthLeft), monthLeft, tone: toneFor(lasts) };
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * «lunes 2» from the API's local date (`YYYY-MM-DD`). The date is the
 * business's own day, so it is read as that calendar day —in UTC, never
 * shifted by the browser's zone—. Another month than this one gets its name:
 * «lunes 2» alone reads as this month's.
 */
export function runsOutDate(iso: string | null, locale: Locale, now: Date): string | null {
  const m = iso ? ISO_DAY.exec(iso) : null;
  if (!m) return null;
  const [year, month] = [Number(m[1]), Number(m[2]) - 1];
  const date = new Date(Date.UTC(year, month, Number(m[3])));
  if (Number.isNaN(date.getTime())) return null;
  const sameMonth = year === now.getFullYear() && month === now.getMonth();
  return new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", {
    weekday: "long",
    day: "numeric",
    ...(sameMonth ? {} : { month: "long" }),
    ...(year === now.getFullYear() ? {} : { year: "numeric" }),
    timeZone: "UTC",
  }).format(date);
}

/** The Inbox with what waits for a person, the first one open (the design's «Atender»). */
export function waitingHref(firstConversationId: string | null): string {
  return firstConversationId ? `/inbox?filter=waiting&c=${encodeURIComponent(firstConversationId)}` : "/inbox?filter=waiting";
}

export type DetailFamilies = { messages: number; model: number; media: number; other: number | null };

function familyOf(meter: string): keyof DetailFamilies {
  if (meter === "channel.message") return "messages";
  if (meter.startsWith("llm.")) return "model";
  if (meter.startsWith("media.")) return "media";
  return "other";
}

/**
 * The technical detail in the three families the client reads (spec 045,
 * R6.3) —messages, model usage, media— from the meters' totals of the
 * period. A meter of none of them goes to «other», which exists only when
 * one is there: an always-empty column says nothing (constitution §V).
 */
export function detailFamilies(totals: Record<string, number>): DetailFamilies {
  const out: DetailFamilies = { messages: 0, model: 0, media: 0, other: null };
  for (const [meter, value] of Object.entries(totals)) {
    const family = familyOf(meter);
    out[family] = (out[family] ?? 0) + value;
  }
  return out;
}
