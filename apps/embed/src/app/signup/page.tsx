"use client";

/**
 * /signup — WhatsApp Embedded Signup inside the widget (ADR-028, Fase 2).
 *
 * Placeholder: the route exists so the SDK's `connectWhatsApp()` has a
 * stable target and the CSP middleware already covers it. Fase 2 ports
 * the admin's Embedded Signup dialog (meta-fb-sdk) here and completes
 * via `POST /v1/embed/whatsapp/signup`.
 */

import { useEffect } from "react";

import { announceReady, connectBridge, postToParent } from "@/lib/bridge";

export default function SignupPage() {
  useEffect(() => {
    const disconnect = connectBridge({
      onInit: () => {
        /* Fase 2: load FB SDK + run Embedded Signup */
      },
      onToken: () => {},
    });
    announceReady();
    return disconnect;
  }, []);

  return (
    <div className="fixed inset-0 flex items-center justify-center p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Conectar WhatsApp"
        className="w-full max-w-md bg-surface p-6 text-center shadow-2xl"
        style={{ borderRadius: "var(--radius-widget)" }}
      >
        <h1 className="text-sm font-semibold">Conectar WhatsApp</h1>
        <p className="mt-2 text-pretty text-sm text-ink-muted">
          La conexión self-serve estará disponible próximamente. Por ahora, tu proveedor conecta el
          número por vos — escribile para coordinar.
        </p>
        <button
          type="button"
          onClick={() => postToParent("auph:close")}
          className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Entendido
        </button>
      </div>
    </div>
  );
}
