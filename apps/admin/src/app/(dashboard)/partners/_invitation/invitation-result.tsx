"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState, useTransition, type ReactNode } from "react";

import { Button, Callout } from "@nexus/ui";

import type { OwnerInvitationResult } from "@/lib/backend";
import { longDate } from "@/lib/format";

import { resendOwnerInvitationAction } from "./actions";
import { DEAD_INVITATION_CODES, RETRY_UNKNOWN, SENDING_HINT } from "./messages";

/**
 * Spec 052, requisito 2: lo que ve el operador tras cada envío. No se va sola:
 * el enlace solo existe en esta vista, y un fallo que desaparece es un alta que
 * se queda esperando. Vive en estado de cliente, así que el enlace no pasa por
 * ninguna URL del panel (R6.6).
 *
 * Es la misma al crear, al invitar y al reenviar. Dice «enviada» y nunca
 * «entregada»: la plataforma solo sabe que el proveedor la aceptó (R2.7).
 */
export function InvitationResult({
  partnerId,
  partnerName,
  result,
  replacedPrevious = false,
  onReplaced,
  onDead,
  lead,
  children,
}: {
  partnerId: string;
  partnerName: string;
  result: OwnerInvitationResult;
  /** Este enlace sustituye a otro, que ya no sirve (R2.4, R4.3). */
  replacedPrevious?: boolean;
  onReplaced: (next: OwnerInvitationResult) => void;
  /** La invitación ya no está viva, y su enlace no debe seguir en pantalla. */
  onDead: (message: string) => void;
  lead?: ReactNode;
  /** La salida: es el operador quien decide irse (R2.1). */
  children?: ReactNode;
}) {
  const [pending, start] = useTransition();
  const [retryError, setRetryError] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);

  // R2.9: el resultado se anuncia (el rol de `Callout`) y recibe el foco, para
  // que quien va con teclado no se quede en un botón que ya no está. También con
  // cada resultado nuevo, cuando un reintento lo sustituye.
  useEffect(() => {
    top.current?.focus();
  }, [result.id]);

  function retry() {
    setRetryError(null);
    start(async () => {
      const r = await resendOwnerInvitationAction(partnerId, result.id);
      if (r.ok) {
        onReplaced(r.data);
        return;
      }
      if (r.code && DEAD_INVITATION_CODES.has(r.code)) {
        onDead(r.error);
        return;
      }
      // Se perdió la respuesta, y el reenvío pudo confirmarse: este enlace estaría
      // muerto, y seguir ofreciéndolo para copiar sería mandar a alguien a un 404.
      if (r.code === "unknown_outcome") {
        onDead(RETRY_UNKNOWN);
        return;
      }
      // Una negativa no toca el enlace (R4.4): sigue vivo, y se queda.
      setRetryError(r.error);
    });
  }

  const until = longDate(result.expires_at);

  return (
    <div className="grid min-w-0 gap-(--space-stack)">
      {lead}
      <div
        ref={top}
        tabIndex={-1}
        className="min-w-0 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        {result.email_sent ? (
          <Callout tone="positive" title={<span className="wrap-anywhere">Invitación enviada a {result.email}</span>}>
            <p>
              Vale hasta el {until}. «Enviada» quiere decir que el proveedor de correo la aceptó: no sabemos si ha
              llegado a su bandeja.
              {replacedPrevious ? " El enlace anterior ya no sirve." : ""}
            </p>
          </Callout>
        ) : (
          <Callout tone="danger" title="El correo no salió">
            <p className="wrap-anywhere">
              {partnerName} y su invitación existen, pero el correo a {result.email} no salió. Este enlace no se volverá
              a mostrar: cópialo y pásaselo por otro medio, o reintenta. Vale hasta el {until}.
              {replacedPrevious ? " El enlace anterior ya no sirve." : ""}
            </p>
          </Callout>
        )}
      </div>

      <div className="grid min-w-0 gap-2">
        {result.email_sent ? (
          <p className="text-sm text-pretty text-muted-foreground">
            El enlace, por si no le llega. Solo se muestra aquí: pásaselo por otro medio.
          </p>
        ) : null}
        {/* Otro enlace, otro «copiado»: el aviso del anterior no vale para este. */}
        <AcceptLink key={result.accept_url} url={result.accept_url} />
      </div>

      {retryError ? <Callout tone="danger">{retryError}</Callout> : null}

      <div className="flex flex-wrap items-center gap-2">
        {result.email_sent ? null : (
          <Button type="button" onClick={retry} loading={pending}>
            {pending ? "Reintentando…" : "Reintentar el envío"}
          </Button>
        )}
        {children}
      </div>
      {pending ? (
        <p role="status" className="text-xs text-pretty text-muted-foreground">
          {SENDING_HINT}
        </p>
      ) : null}
    </div>
  );
}

function AcceptLink({ url }: { url: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <div className="grid min-w-0 gap-1">
      <div className="flex min-w-0 flex-wrap items-start gap-2">
        <code className="min-w-0 flex-1 basis-60 rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs break-all select-all">
          {url}
        </code>
        <Button type="button" variant="outline" onClick={copy} aria-label="Copiar el enlace de invitación">
          {state === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {state === "copied" ? "Copiado" : "Copiar"}
        </Button>
      </div>
      <p aria-live="polite" className="min-h-4 text-xs text-muted-foreground">
        {state === "copied" ? "Enlace copiado" : null}
        {state === "failed" ? "No se pudo copiar: selecciona el enlace y cópialo a mano." : null}
      </p>
    </div>
  );
}
