"use client";

import { Bot, Minus, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, StatusBadge, cn } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";
import type { ActionResult } from "@/lib/actions";
import type { Booking } from "@/lib/backend/reservas";

import { useReservas } from "./context";
import { failureMessage, initialsOf, statusKey, statusTone } from "./model/vocab";

/**
 * Small pieces every Reservas screen uses: chips, the −/+ stepper, the
 * two-way switches of the toolbar, the status pill, initials, and the one
 * way a write tells the person how it went.
 */

export function Chip({
  pressed,
  className,
  children,
  ...props
}: Omit<React.ComponentProps<"button">, "type"> & { pressed: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      className={cn(
        "inline-flex h-8 max-w-full min-w-0 shrink-0 items-center justify-center gap-1 rounded-full border px-3 text-sm whitespace-nowrap",
        "transition-colors duration-(--duration-hover) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        pressed
          ? "border-transparent bg-accent font-medium text-accent-foreground"
          : "border-border bg-background text-foreground hover:bg-muted",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/** A labelled group of chips (`role=group`): one choice at a time, each chip says if it is the one. */
export function ChipGroup({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div role="group" aria-label={label} className={cn("flex min-w-0 flex-wrap gap-2", className)}>
      {children}
    </div>
  );
}

/**
 * Two or three options side by side: Día · Semana · Mes, Cuadrícula · Lista.
 * When a translation does not fit (360 px, a longer language), the options
 * wrap inside the group instead of pushing the page sideways.
 */
export function Segmented<V extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: V;
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex max-w-full shrink-0 flex-wrap rounded-md border border-border bg-background p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex h-7 items-center rounded-sm px-3 text-sm whitespace-nowrap transition-colors duration-(--duration-hover)",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
            o.value === value ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** −/+ with the value between. The value is read aloud with its label. */
export function Stepper({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  display,
  id,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min: number;
  max?: number;
  step?: number;
  /** How the value reads («Ninguna» for 0 held seats). */
  display?: string;
  id?: string;
}) {
  const { t } = useReservas();
  const clamp = (n: number) => Math.max(min, max === undefined ? n : Math.min(max, n));
  return (
    <div className="inline-flex items-center gap-2" role="group" aria-label={label}>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={t("reservas.stepper.less", { label })}
        disabled={value <= min}
        onClick={() => onChange(clamp(value - step))}
      >
        <Minus aria-hidden="true" />
      </Button>
      <output id={id} aria-live="polite" className="min-w-12 text-center text-base font-semibold tabular-nums">
        {display ?? value}
      </output>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={t("reservas.stepper.more", { label })}
        disabled={max !== undefined && value >= max}
        onClick={() => onChange(clamp(value + step))}
      >
        <Plus aria-hidden="true" />
      </Button>
    </div>
  );
}

export function BookingStatus({ booking, className }: { booking: Pick<Booking, "status">; className?: string }) {
  const { t, mode } = useReservas();
  return (
    <StatusBadge tone={statusTone(booking.status)} className={className}>
      {t(statusKey(mode, booking.status))}
    </StatusBadge>
  );
}

export function Initials({ name, className }: { name: string | null | undefined; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground",
        className,
      )}
    >
      {initialsOf(name)}
    </span>
  );
}

/** The agent's mark on what it booked; the words are there for a screen reader. */
export function AgentMark({ className }: { className?: string }) {
  const { t } = useReservas();
  return (
    <span className={cn("inline-flex shrink-0", className)} title={t("reservas.grid.agent")}>
      <Bot className="size-3" aria-hidden="true" />
      <span className="sr-only">{t("reservas.grid.agent")}</span>
    </span>
  );
}

export type Outcome<T> = { ok: true; data: T } | { ok: false; status: number; code?: string | null; info?: Record<string, unknown> };

/**
 * One write, told well: success says what happened, a refusal says why in
 * the person's words (never the API's text), and a stale version reloads what
 * is there now. Returns the action's result for the caller to go on.
 */
export function useWrite() {
  const { t, refresh } = useReservas();
  return React.useCallback(
    async <D,>(
      fn: () => Promise<ActionResult<D>>,
      opts: { success?: string | ((data: D) => string); refreshOnOk?: boolean; quiet?: boolean } = {},
    ): Promise<Outcome<D>> => {
      let res: ActionResult<D>;
      try {
        res = await fn();
      } catch {
        if (!opts.quiet) toast.error(t("common.error.backend"));
        return { ok: false, status: 0 };
      }
      if (res.ok) {
        const msg = typeof opts.success === "function" ? opts.success(res.data) : opts.success;
        if (msg) toast.success(msg);
        if (opts.refreshOnOk !== false) refresh();
        return res;
      }
      if (!opts.quiet) {
        const f = failureMessage(res);
        toast.error(t(f.key as MessageKey, f.vars));
      }
      if (res.status === 412 || (res.status === 409 && res.code === "invalid_transition")) refresh();
      return res;
    },
    [t, refresh],
  );
}
