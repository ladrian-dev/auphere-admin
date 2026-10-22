"use client";

import Link from "next/link";
import type * as React from "react";

import { cn } from "@nexus/ui";

import type { Booking } from "@/lib/backend/reservas";

import { useReservas } from "../context";
import { fromMinutes } from "../model/dates";
import {
  GRID_STEP,
  bookingSpan,
  bookingTone,
  cellKind,
  gapsOf,
  gridRows,
  holdsTime,
  placeInLanes,
  type BookingTone,
  type Span,
} from "../model/day-grid";
import { statusKey } from "../model/vocab";
import type { HeldSlot } from "../model/waitlist";
import { AgentMark } from "../shared";

/** 28 px per 30 min: the design's 56 px per hour. */
const ROW_PX = 28;

export type GridColumn = {
  key: string;
  date: string;
  staff: { id: string; name: string } | null;
  header: React.ReactNode;
  /** Working ranges of the column; empty = closed all day. */
  spans: Span[];
  bookings: Booking[];
  /** Slots being offered to the waitlist right now: held, dashed, not bookable. */
  held?: HeldSlot[];
  highlight?: boolean;
  /** The free cell's name for a screen reader. */
  freeLabel: (time: string) => string;
};

/** Each status looks like the design: confirmed light green, pending dashed, in course dark, done grey, no-show light red. */
export const TONE_CLASS: Record<BookingTone, string> = {
  confirmed: "border-primary/40 bg-primary/15 text-foreground",
  pending: "border-dashed border-input bg-card text-foreground",
  inCourse: "border-transparent bg-primary-deep text-fg-on-dark",
  arrived: "border-primary/40 bg-primary/30 text-foreground",
  done: "border-border bg-muted text-muted-foreground",
  noshow: "border-status-danger-border bg-status-danger-bg text-foreground",
  cancelled: "border-border bg-muted text-muted-foreground line-through",
  clash: "border-status-warning-border bg-status-warning-bg text-foreground",
};

/** A held slot looks like what it is: a place kept open, dashed, in the «not yet» tone (design §3.1). */
const HELD_CLASS = "border-dashed border-status-info/60 bg-status-info/10 text-foreground";

const px = (minutes: number, from: number) => ((minutes - from) / GRID_STEP) * ROW_PX;

type Block = { kind: "booking"; booking: Booking } | { kind: "held"; held: HeldSlot };
const blockSpan = (b: Block): Span => bookingSpan(b.kind === "booking" ? b.booking : b.held);

/**
 * The time grid of Servicios (spec 043, T023): a column per professional (a
 * day) or per day (one professional's week). Rows of 30 min; what is not
 * working time says «Pausa» or «Cerrado»; overlapping bookings share the
 * width in lanes; a free cell offers «+ HH:MM» on hover and on focus and opens
 * «Nueva reserva» with everything set. Past and closed cells do not answer.
 * A slot being offered to the waitlist is held — «Ofreciendo el hueco · Lista
 * de espera · i de n» — and leads to the waitlist tab.
 *
 * The grid scrolls sideways inside its own frame: at 360 px the page itself
 * never does.
 */
export function TimeGrid({ label, columns, bounds, onFree }: { label: string; columns: GridColumn[]; bounds: Span; onFree: (c: GridColumn, time: string) => void }) {
  const { t, today, nowMinutes, mode, open, href } = useReservas();
  const rows = gridRows(bounds);
  const height = rows.length * ROW_PX;
  const showNow = columns.some((c) => c.date === today) && nowMinutes >= bounds.from && nowMinutes < bounds.to;

  return (
    <section aria-label={label} className="min-w-0 overflow-x-auto rounded-md border border-border bg-card">
      <div
        className="grid min-w-max"
        style={{ gridTemplateColumns: `3.5rem repeat(${columns.length}, minmax(10rem, 1fr))` }}
      >
        <div aria-hidden="true" className="border-b border-border" />
        {columns.map((c) => (
          <div
            key={c.key}
            className={cn("flex min-w-0 items-center gap-2 border-b border-l border-border px-3 py-2", c.highlight && "bg-accent/40")}
          >
            {c.header}
          </div>
        ))}

        {/* The hours of the left margin, and the «now» marker. */}
        <div className="relative" style={{ height }}>
          {rows
            .filter((m) => m % 60 === 0)
            .map((m) => (
              <span
                key={m}
                className="absolute right-2 -translate-y-1/2 text-xs text-muted-foreground tabular-nums first:translate-y-0"
                style={{ top: px(m, bounds.from) }}
              >
                {fromMinutes(m)}
              </span>
            ))}
          {showNow ? (
            <span
              className="absolute right-1 -translate-y-1/2 rounded-sm bg-destructive px-1 text-xs font-medium text-destructive-foreground tabular-nums"
              style={{ top: px(nowMinutes, bounds.from) }}
            >
              <span className="sr-only">{t("reservas.grid.now", { time: fromMinutes(nowMinutes) })}</span>
              <span aria-hidden="true">{fromMinutes(nowMinutes)}</span>
            </span>
          ) : null}
        </div>

        {columns.map((c) => {
          const blocks: Block[] = [
            ...c.bookings.filter(holdsTime).map((booking) => ({ kind: "booking" as const, booking })),
            ...(c.held ?? []).map((held) => ({ kind: "held" as const, held })),
          ];
          const busy = blocks.map(blockSpan);
          const past = (start: number) => c.date < today || (c.date === today && start < nowMinutes);
          const placed = placeInLanes(blocks, blockSpan);
          return (
            <div key={c.key} role="group" aria-label={c.staff?.name ?? undefined} className="relative border-l border-border" style={{ height }}>
              {/* Half-hour lines. */}
              {rows.map((m) => (
                <div
                  key={m}
                  aria-hidden="true"
                  className={cn("absolute inset-x-0 border-t", m % 60 === 0 ? "border-border" : "border-border-soft")}
                  style={{ top: px(m, bounds.from) }}
                />
              ))}
              {gapsOf(c.spans, bounds).map((g) => (
                <div
                  key={`${g.kind}-${g.from}`}
                  className="absolute inset-x-0 flex items-start justify-center overflow-hidden bg-muted/70 pt-1 text-xs text-muted-foreground"
                  style={{ top: px(g.from, bounds.from), height: px(g.to, bounds.from) - px(g.from, bounds.from) }}
                >
                  {px(g.to, bounds.from) - px(g.from, bounds.from) >= ROW_PX ? t(g.kind === "pause" ? "reservas.grid.pause" : "reservas.grid.closed") : null}
                </div>
              ))}
              {rows.map((m) =>
                cellKind(m, { spans: c.spans, busy, past }) === "free" ? (
                  <button
                    key={`free-${m}`}
                    type="button"
                    aria-label={c.freeLabel(fromMinutes(m))}
                    onClick={() => onFree(c, fromMinutes(m))}
                    className={cn(
                      "absolute inset-x-1 flex items-center rounded-sm px-2 text-xs font-medium text-primary-text opacity-0",
                      "transition-opacity duration-(--duration-hover) hover:bg-primary/10 hover:opacity-100",
                      "focus-visible:bg-primary/10 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-ring",
                    )}
                    style={{ top: px(m, bounds.from) + 2, height: ROW_PX - 4 }}
                  >
                    {t("reservas.grid.free", { time: fromMinutes(m) })}
                  </button>
                ) : null,
              )}
              {placed.map(({ item, lane, lanes }) => {
                const s = blockSpan(item);
                const top = px(Math.max(s.from, bounds.from), bounds.from);
                // Never under 24 px tall once drawn (WCAG 2.5.8), even for a 15-min booking.
                const h = Math.max(px(Math.min(s.to, bounds.to), bounds.from) - top, ROW_PX);
                const place = {
                  top: top + 1,
                  height: h - 2,
                  left: `calc(${(lane / lanes) * 100}% + 2px)`,
                  width: `calc(${100 / lanes}% - 4px)`,
                };
                if (item.kind === "held") {
                  const o = item.held;
                  const label = o.index > 0 ? t("reservas.grid.held", { index: o.index, total: o.total }) : t("reservas.grid.held.plain");
                  return (
                    <Link
                      key={`held-${o.id}`}
                      href={href({ tab: "waitlist" })}
                      aria-label={t("reservas.grid.held.aria", { from: o.local.start, to: o.local.end, label })}
                      className={cn(
                        "absolute flex min-w-0 flex-col items-start overflow-hidden rounded-sm border px-2 py-1 text-left text-xs",
                        "focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                        HELD_CLASS,
                      )}
                      style={place}
                    >
                      <span className="shrink-0 tabular-nums">{o.local.start}</span>
                      <span className="w-full font-medium text-pretty">{label}</span>
                    </Link>
                  );
                }
                const b = item.booking;
                const tone = bookingTone(b, today, nowMinutes);
                const name = b.contact.name ?? "";
                return (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => open({ kind: "detail", id: b.id, booking: b })}
                    aria-label={t("reservas.grid.booking.aria", {
                      from: b.local.start,
                      to: b.local.end,
                      name,
                      service: b.service?.name ?? "",
                      status: tone === "inCourse" ? t("reservas.status.inCourse") : t(statusKey(mode, b.status)),
                    })}
                    className={cn(
                      "absolute flex min-w-0 flex-col items-start overflow-hidden rounded-sm border px-2 py-1 text-left text-xs",
                      "focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                      TONE_CLASS[tone],
                    )}
                    style={place}
                  >
                    <span className="flex w-full min-w-0 items-center gap-1">
                      <span className="shrink-0 tabular-nums">{b.local.start}</span>
                      <span className="min-w-0 truncate font-medium">{name}</span>
                      {b.origin === "agent" ? <AgentMark className="ml-auto" /> : null}
                    </span>
                    {h >= ROW_PX * 2 && b.service ? <span className="w-full truncate opacity-80">{b.service.name}</span> : null}
                    {b.clash && h >= ROW_PX * 2 ? (
                      <span className="w-full truncate">{t("reservas.grid.clash", { time: b.clash.local.start })}</span>
                    ) : null}
                  </button>
                );
              })}
              {showNow && c.date === today ? (
                <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 border-t-2 border-destructive" style={{ top: px(nowMinutes, bounds.from) }} />
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
