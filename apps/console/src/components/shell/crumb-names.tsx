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

/**
 * `transient`: el nombre se va al desmontar. Lo usa la configuración de un
 * canal dentro de su agente (`?canal=`, 63.1): cerrada, la miga del canal no
 * se queda.
 */
export function CrumbName({ id, label, transient = false }: { id: string; label: string; transient?: boolean }) {
  useEffect(() => {
    names = { ...names, [id]: label };
    emit();
    if (!transient) return;
    return () => {
      const rest = { ...names };
      delete rest[id];
      names = rest;
      emit();
    };
  }, [id, label, transient]);
  return null;
}

/** La clave con la que la configuración de un canal anuncia su miga dentro de su agente. */
export function openChannelCrumb(agentId: string): string {
  return `canal@${agentId}`;
}
