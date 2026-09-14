"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";

import { resendSignupAction } from "./actions";

/**
 * Reenviar el enlace del alta (R8.2).
 *
 * **Deshabilitado no es invisible, aquí a propósito.** En la consola de partner
 * la ausencia se diseña porque quien mira no puede hacer nada al respecto; aquí
 * mira un operador, y que el botón exista pero no se pueda pulsar *es*
 * información: esta solicitud ya no está viva. Por eso lleva su motivo en el
 * título accesible en vez de desaparecer.
 */
export function ResendButton({ signupId, enabled }: { signupId: string; enabled: boolean }) {
  const [pending, start] = React.useTransition();
  const [msg, setMsg] = React.useState<string | null>(null);

  if (!enabled) {
    return (
      <Button size="sm" variant="ghost" disabled title="Sólo se reenvía una solicitud viva">
        Reenviar
      </Button>
    );
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <Button
        size="sm"
        variant="outline"
        disabled={pending}
        onClick={() =>
          start(async () => {
            const r = await resendSignupAction(signupId);
            setMsg(r.ok ? "Enlace nuevo enviado" : r.error);
          })
        }
      >
        {pending ? "Enviando…" : "Reenviar"}
      </Button>
      {/* `role="status"` y no un toast: el resultado de una acción sobre una
          fila concreta se lee junto a esa fila, y un lector de pantalla lo
          anuncia sin robar el foco. */}
      {msg ? (
        <span role="status" className="max-w-[22rem] text-pretty text-xs text-muted-foreground">
          {msg}
        </span>
      ) : null}
    </span>
  );
}
