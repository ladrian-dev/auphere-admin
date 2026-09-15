"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { googleStartAction } from "@/lib/auth-actions";

/**
 * «Continuar con Google» — spec 006, Requisito 5.6.
 *
 * **Si Google no está disponible, este botón desaparece; no se queda gris.**
 * La ausencia se diseña (constitución §V), y el alta y el login con contraseña
 * siguen funcionando sin él, que es justo lo que el requisito pide.
 *
 * **La disponibilidad llega resuelta desde el servidor, y eso es deliberado.**
 * Antes se comprobaba al montar llamando a `googleStartAction`, que es el que
 * EMPIEZA un inicio de sesión: acuña un par PKCE y lo guarda diez minutos en
 * Redis. Como preguntaba al montar y volvía a llamar al pulsar, cada visita a
 * `/login` —una página pública— dejaba una clave que nadie iba a consumir. El
 * comentario que había aquí decía «una llamada que no crea nada»; era falso.
 *
 * De paso desaparece el parpadeo: ya no hay un instante de «todavía no se
 * sabe», porque la página se renderiza con la respuesta dentro.
 */
export function GoogleButton({
  intent,
  available,
  returnTo,
}: {
  intent: "login" | "signup";
  available: boolean;
  /** A dónde volver tras entrar — spec 009, fallo 1.
   *
   *  Sin esto, quien entra con Google desde `/login?from=…` acaba en la portada
   *  y la aplicación de escritorio se queda esperando: el camino de correo y
   *  contraseña conservaba el destino y éste lo perdía en este botón. */
  returnTo?: string;
}) {
  const t = useT();
  const [pending, startTransition] = React.useTransition();

  if (!available) return null;

  function go() {
    startTransition(async () => {
      const url = await googleStartAction(intent, returnTo);
      if (!url) {
        toast.error(t("common.error.backend"));
        return;
      }
      window.location.assign(url);
    });
  }

  return (
    <Button type="button" variant="outline" onClick={go} disabled={pending} className="w-full">
      {t("auth.google")}
    </Button>
  );
}
