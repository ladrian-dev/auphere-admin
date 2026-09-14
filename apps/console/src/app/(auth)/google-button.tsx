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
 * Se comprueba al montar con una llamada que no crea nada: si la API responde
 * que Google no está configurado, `googleStartAction` devuelve `null` y aquí
 * no se pinta nada.
 */
export function GoogleButton({ intent }: { intent: "login" | "signup" }) {
  const t = useT();
  const [available, setAvailable] = React.useState<boolean | null>(null);
  const [pending, startTransition] = React.useTransition();

  React.useEffect(() => {
    let alive = true;
    googleStartAction(intent)
      .then((url) => alive && setAvailable(url !== null))
      .catch(() => alive && setAvailable(false));
    return () => {
      alive = false;
    };
  }, [intent]);

  // `null` es «todavía no se sabe»: no se pinta un botón que quizá haya que
  // quitar, porque aparecer y desaparecer es peor que tardar un momento.
  if (available !== true) return null;

  function go() {
    startTransition(async () => {
      const url = await googleStartAction(intent);
      if (!url) {
        toast.error(t("common.error.backend"));
        setAvailable(false);
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
