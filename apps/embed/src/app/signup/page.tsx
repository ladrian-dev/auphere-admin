"use client";

/**
 * /signup — WhatsApp Embedded Signup inside the widget (ADR-028, Fase 2).
 *
 * Flow: handshake (auph:ready → auph:init with token) → the user clicks
 * "Conectar" → `FB.login` popup under OUR origin + Meta config → the
 * envelope (code + waba/phone ids) goes to `POST /v1/embed/whatsapp/
 * signup` with the session token → on success we emit `auph:connected`
 * so the loader flips status and the partner's broadcast button appears.
 *
 * The Meta App ID + configuration ID are public identifiers (they ship
 * in every embedding page); the secrets never leave the backend.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, completeSignup } from "@/lib/api";
import { announceReady, connectBridge, postToParent } from "@/lib/bridge";
import { loginWithMeta, META_CONFIG_ID_CLOUD_API } from "@/lib/meta-fb-sdk";

type Phase =
  | { name: "handshake" }
  | { name: "ready" }
  | { name: "popup" }
  | { name: "completing" }
  | { name: "done"; displayPhoneNumber: string; tenantActivated: boolean }
  | { name: "error"; message: string; retryable: boolean };

export default function SignupPage() {
  const [phase, setPhase] = useState<Phase>({ name: "handshake" });

  useEffect(() => {
    const disconnect = connectBridge({
      onInit: (payload) => {
        const body = document.body;
        if (payload.appearance.colorPrimary) {
          body.style.setProperty("--auph-accent", payload.appearance.colorPrimary);
        }
        if (payload.appearance.radius) {
          body.style.setProperty("--auph-radius", payload.appearance.radius);
        }
        setPhase({ name: "ready" });
      },
      onToken: () => {
        // Fresh token in memory — a 401 error state can be retried.
      },
    });
    announceReady();
    return disconnect;
  }, []);

  const connect = useCallback(async () => {
    if (!META_CONFIG_ID_CLOUD_API) {
      setPhase({
        name: "error",
        message: "El widget no está configurado para conexión self-serve (falta configuration ID).",
        retryable: false,
      });
      return;
    }
    setPhase({ name: "popup" });
    let envelope;
    try {
      envelope = await loginWithMeta(META_CONFIG_ID_CLOUD_API, "cloud_api");
    } catch (error) {
      setPhase({
        name: "error",
        message: error instanceof Error ? error.message : "No se pudo completar el flow de Meta.",
        retryable: true,
      });
      return;
    }
    setPhase({ name: "completing" });
    try {
      const result = await completeSignup({ ...envelope, mode: "cloud_api" });
      setPhase({
        name: "done",
        displayPhoneNumber: result.display_phone_number,
        tenantActivated: result.tenant_activated,
      });
      postToParent("auph:connected", { displayPhoneNumber: result.display_phone_number });
    } catch (error) {
      setPhase({
        name: "error",
        message:
          error instanceof ApiError ? error.detail : "No se pudo registrar la conexión. Intenta de nuevo.",
        retryable: true,
      });
    }
  }, []);

  const close = useCallback(() => postToParent("auph:close"), []);

  return (
    <div className="fixed inset-0 flex items-center justify-center p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Conectar WhatsApp"
        className="w-full max-w-md bg-surface p-6 shadow-2xl"
        style={{ borderRadius: "var(--radius-widget)" }}
      >
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span aria-hidden className="inline-block size-2.5 rounded-full bg-accent" />
            <h1 className="text-sm font-semibold tracking-tight">Conectar WhatsApp</h1>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Cerrar"
            className="rounded-md p-1.5 text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <main className="mt-4">
          {phase.name === "handshake" && (
            <p className="text-sm text-ink-muted" role="status">
              Preparando la conexión…
            </p>
          )}

          {phase.name === "ready" && (
            <>
              <p className="text-pretty text-sm text-ink-muted">
                Conecta el número de WhatsApp de tu negocio para enviar recordatorios y atender a
                tus clientes. Se abrirá una ventana de Meta donde autorizas la conexión con la
                cuenta de tu negocio.
              </p>
              <ul className="mt-3 space-y-1.5 text-sm text-ink-muted">
                <li className="flex items-start gap-2">
                  <CheckIcon />
                  Necesitas acceso al Meta Business de tu negocio.
                </li>
                <li className="flex items-start gap-2">
                  <CheckIcon />
                  El número queda conectado solo para tu negocio.
                </li>
              </ul>
              <button
                type="button"
                onClick={() => void connect()}
                className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Conectar con Meta
              </button>
            </>
          )}

          {phase.name === "popup" && (
            <p className="text-sm text-ink-muted" role="status">
              Completa la autorización en la ventana de Meta. Esta pantalla se actualizará sola al
              terminar.
            </p>
          )}

          {phase.name === "completing" && (
            <p className="text-sm text-ink-muted" role="status">
              Registrando la conexión…
            </p>
          )}

          {phase.name === "done" && (
            <div role="status">
              <p className="text-sm font-medium">
                WhatsApp conectado: <span className="tabular-nums">{phase.displayPhoneNumber}</span>
              </p>
              <p className="mt-2 text-pretty text-sm text-ink-muted">
                {phase.tenantActivated
                  ? "Tu asistente ya está activo y responde en este número."
                  : "La conexión quedó registrada. Tu asistente se activará en breve."}
              </p>
              <button
                type="button"
                onClick={close}
                className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Listo
              </button>
            </div>
          )}

          {phase.name === "error" && (
            <div role="alert">
              <p className="text-pretty text-sm text-ink">{phase.message}</p>
              <div className="mt-5 flex gap-2">
                {phase.retryable && (
                  <button
                    type="button"
                    onClick={() => void connect()}
                    className="flex-1 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    Reintentar
                  </button>
                )}
                <button
                  type="button"
                  onClick={close}
                  className="flex-1 rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  Cerrar
                </button>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function CheckIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
      className="mt-0.5 shrink-0 text-accent"
    >
      <path
        d="M3 8.5l3.5 3.5L13 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
