"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * Spec 047 (R47.1): los nombres de las migas. Una página que conoce el nombre
 * de lo que enseña (el cliente, el agente, el canal) pinta
 * `<CrumbName id={ref} label={nombre} />` y la barra superior lo lee. Un
 * almacén mínimo fuera del estado de React: anunciar un nombre no vuelve a
 * pintar la página. El mismo patrón que el panel de operador (spec 035).
 */
let names: Record<string, string> = {};
const listeners = new Set<() => void>();
const EMPTY: Record<string, string> = {};

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

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
