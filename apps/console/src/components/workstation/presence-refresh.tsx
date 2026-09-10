"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

/**
 * La presencia se deriva del latido (cada 10 s) y la página es de servidor:
 * sin esto, «conectada» solo aparecía al recargar. Refresca los datos del
 * servidor con la cadencia del latido mientras la pestaña está visible; no
 * toca el estado del cliente ni los diálogos abiertos.
 */
export function PresenceRefresh({ intervalMs = 10_000 }: { intervalMs?: number }) {
  const router = useRouter();
  React.useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") router.refresh();
    };
    const timer = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(timer);
  }, [router, intervalMs]);
  return null;
}
