"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * Names for the breadcrumb's record segments. A page that knows a record's
 * name (the client's layout, a channel's page) renders `<CrumbName>` and the
 * top bar reads it. A tiny external store keeps it out of React state, so a
 * page announcing its name never re-renders the page itself.
 */
let names: Record<string, string> = {};
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const EMPTY: Record<string, string> = {};

export function useCrumbNames(): Record<string, string> {
  return useSyncExternalStore(subscribe, () => names, () => EMPTY);
}

export function CrumbName({ id, label }: { id: string; label: string }) {
  useEffect(() => {
    names = { ...names, [id]: label };
    emit();
  }, [id, label]);
  return null;
}
