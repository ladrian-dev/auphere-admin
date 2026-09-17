"use client";

import { useEffect } from "react";

export interface ToastProps {
  message: string | null;
  onDismiss: () => void;
  durationMs?: number;
}

/** Aviso breve no bloqueante. Región aria-live siempre presente. */
export function Toast({ message, onDismiss, durationMs = 5000 }: ToastProps) {
  useEffect(() => {
    if (!message) return;
    const t = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(t);
  }, [message, onDismiss, durationMs]);

  return (
    <div aria-live="polite" aria-atomic="true" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex justify-center px-4">
      {message ? (
        <div className="pointer-events-auto max-w-md rounded-md bg-surface-strong px-4 py-3 text-sm text-ink-on-strong shadow-3 fade-up">
          {message}
          <button type="button" onClick={onDismiss} className="ml-3 underline underline-offset-2">
            Cerrar
          </button>
        </div>
      ) : null}
    </div>
  );
}
