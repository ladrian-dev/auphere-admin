import { useSyncExternalStore } from "react";

import type { LocalDate } from "@/lib/reservas-model";

/**
 * Micro 3 for Reservas (spec 069, R15.4): a booking just saved — or moved —
 * enters its day animated. The form closes and Reservas, still mounted under
 * it, goes to that day and lets that one row arrive; nothing else animates.
 * A signal, not state of a screen: the form and the day never share a tree.
 * It expires on its own (a timer clears it and tells the screens), so a later
 * visit neither animates the row again nor jumps back to that day.
 */
type Arrival = { id: string; date: LocalDate; seq: number };

/** How long a row may still arrive after the save: the read that brings it, not a later visit. */
const FRESH_MS = 4000;

let current: Arrival | null = null;
let seq = 0;
let expiry: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();
const emit = () => {
  for (const l of listeners) l();
};

export function announceArrival(id: string, date: LocalDate): void {
  seq += 1;
  current = { id, date, seq };
  if (expiry) clearTimeout(expiry);
  expiry = setTimeout(() => {
    current = null;
    expiry = null;
    emit();
  }, FRESH_MS);
  emit();
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

/** The arrival still fresh, or `null`. */
export function useArrivalSignal(): Arrival | null {
  return useSyncExternalStore(subscribe, () => current, () => current);
}

/** Whether a row should arrive: it is the one just saved, while that is fresh. */
export function arrives(arrival: Arrival | null, id: string): boolean {
  return arrival !== null && arrival.id === id;
}

/** For tests. */
export function resetArrival(): void {
  if (expiry) clearTimeout(expiry);
  expiry = null;
  current = null;
  emit();
}
