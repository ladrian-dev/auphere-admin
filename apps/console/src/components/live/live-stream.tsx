"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { inboxStreamUrl } from "@/lib/inbox-urls";
import { keys } from "@/lib/query";

/**
 * The console's live line (spec 082, R3.11): **one** `EventSource` per tab on
 * the BFF route the Inbox already used (spec 030, D17), shared by the agenda,
 * the unread counter, the sound and the Inbox. Events say WHAT changed, never
 * the text: whoever hears one re-reads through its RLS routes.
 *
 * - `reservations.changed` makes `["reservas"]` stale, a burst being one
 *   re-read (R1.7).
 * - A conversation event makes `["inbox","counts"]` stale (R3.7).
 * - Back after a drop (an open after an error) everything live is re-read and
 *   subscribers hear `back`, so the open Inbox re-reads its list and its
 *   conversation (R3.10).
 * - The browser retries a dropped line on its own, but gives up for good when
 *   a retry gets anything but a 200 with `text/event-stream` (a 502 during a
 *   deploy): the source is left `CLOSED`. Then this closes it and opens
 *   another after 1, 2, 5, 10 and at most 30 s, back to 1 s once one opens.
 *
 * Mounted only for a client person with the Inbox or Reservas; the API
 * forwards each person only the events of their modules (R1.11).
 */
export type LiveName = "conversation.updated" | "message.new" | "message.status" | "reservations.changed";
export type LiveEvent =
  | { name: LiveName; data: Record<string, unknown> }
  /** The line dropped: the session may have ended (the caller checks it). */
  | { name: "down" }
  /** The line is back after a drop: what changed meanwhile was missed. */
  | { name: "back" };
export type LiveStatus = "off" | "connecting" | "live" | "reconnecting";
type Listener = (e: LiveEvent) => void;
type Live = { status: LiveStatus; subscribe: (fn: Listener) => () => void };

const NAMES: readonly LiveName[] = ["conversation.updated", "message.new", "message.status", "reservations.changed"];
/** A burst of notices is one re-read (R1.7, R3.7). */
export const RESERVAS_DEBOUNCE_MS = 300;
export const COUNTS_DEBOUNCE_MS = 400;
/** The waits before opening a line the browser left closed; the last one repeats. */
export const REOPEN_MS: readonly number[] = [1_000, 2_000, 5_000, 10_000, 30_000];

const OFF: Live = { status: "off", subscribe: () => () => undefined };
const Ctx = React.createContext<Live>(OFF);

export function LiveStreamProvider({ enabled, children }: { enabled: boolean; children: React.ReactNode }) {
  const qc = useQueryClient();
  const listeners = React.useRef(new Set<Listener>());
  const [status, setStatus] = React.useState<LiveStatus>(enabled ? "connecting" : "off");

  React.useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const emit = (e: LiveEvent) => {
      for (const fn of [...listeners.current]) fn(e);
    };
    const timers: Partial<Record<"reservas" | "counts", number>> = {};
    const later = (key: "reservas" | "counts", ms: number, fn: () => void) => {
      window.clearTimeout(timers[key]);
      timers[key] = window.setTimeout(fn, ms);
    };
    let isDown = false;
    let failures = 0;
    let reopen: number | undefined;
    const up = () => {
      failures = 0;
      setStatus("live");
      if (!isDown) return;
      isDown = false;
      void qc.invalidateQueries({ queryKey: keys.reservas });
      void qc.invalidateQueries({ queryKey: keys.inbox });
      emit({ name: "back" });
    };
    const handlers = NAMES.map((name) => {
      const handler = (msg: MessageEvent<string>) => {
        let data: Record<string, unknown>;
        try {
          const parsed: unknown = JSON.parse(msg.data);
          if (!parsed || typeof parsed !== "object") return;
          data = parsed as Record<string, unknown>;
        } catch {
          return; // a malformed frame is ignored, never painted
        }
        if (name === "reservations.changed") {
          later("reservas", RESERVAS_DEBOUNCE_MS, () => void qc.invalidateQueries({ queryKey: keys.reservas }));
        } else {
          later("counts", COUNTS_DEBOUNCE_MS, () => void qc.invalidateQueries({ queryKey: keys.inboxCounts }));
        }
        emit({ name, data });
      };
      return [name, handler as EventListener] as const;
    });
    const shut = (es: EventSource) => {
      for (const [name, handler] of handlers) es.removeEventListener(name, handler);
      es.removeEventListener("ready", up);
      es.onopen = null;
      es.onerror = null;
      es.close();
    };
    let source: EventSource;
    const open = () => {
      const es = new EventSource(inboxStreamUrl);
      source = es;
      es.onopen = up;
      es.onerror = () => {
        if (!isDown) {
          isDown = true;
          emit({ name: "down" });
        }
        setStatus("reconnecting");
        // CONNECTING: the browser is retrying on its own. CLOSED: it gave up for good.
        if (es.readyState !== EventSource.CLOSED) return;
        shut(es);
        const wait = REOPEN_MS[Math.min(failures, REOPEN_MS.length - 1)];
        failures += 1;
        reopen = window.setTimeout(open, wait);
      };
      for (const [name, handler] of handlers) es.addEventListener(name, handler);
      es.addEventListener("ready", up);
    };
    open();
    return () => {
      window.clearTimeout(reopen);
      window.clearTimeout(timers.reservas);
      window.clearTimeout(timers.counts);
      shut(source);
    };
  }, [enabled, qc]);

  const subscribe = React.useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);
  const value = React.useMemo<Live>(() => (enabled ? { status, subscribe } : OFF), [enabled, status, subscribe]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** The shared line. Outside the provider (a partner, a test) it is `off` and says nothing. */
export function useLiveStream(): Live {
  return React.useContext(Ctx);
}
