/**
 * La versión nueva — spec 010, Requisitos 6.1, 6.2 y 6.3.
 *
 * El anexo 04 lo dejó por escrito: «se descarga en silencio y **no se dice**».
 * El ciclo entero funcionaba —comprobaba el canal, descargaba, instalaba al
 * salir— y su resultado sólo llegaba al registro. La persona se enteraba de que
 * había una versión nueva al reiniciar, si se enteraba.
 *
 * Tres decisiones:
 *
 * * **banner, no diálogo.** Una versión nueva no es urgente: interrumpir lo que
 *   estabas haciendo para anunciarla es cómo se aprende a cerrar los avisos de
 *   actualización sin leerlos;
 * * **se nombra la versión.** «Hay una nueva» sin número no deja comprobar nada
 *   ni contarlo a soporte;
 * * **«esperando a que termines» se dice.** Es el estado que existía en el tipo
 *   y no se pintaba jamás: con trabajo vivo la instalación no va, y callarlo
 *   deja el botón pareciendo roto.
 */
import { useState } from "react";

import { Button } from "@nexus/ui";

import type { UpdateView } from "../bridge";
import { bridge } from "../bridge";
import { useAppT } from "../i18n";

export function UpdateBanner({ update }: { update: UpdateView | null }) {
  const t = useAppT();
  const [busy, setBusy] = useState(false);

  // Mientras descarga no se dice nada: nada ha cambiado todavía para nadie, y
  // una barra de progreso de algo que no pediste es ruido (§V).
  if (!update || update.state === "idle" || update.state === "descargando") return null;

  const version = update.version ?? "";
  const waiting = update.state === "esperando_trabajo";

  return (
    /* Lo anuncia la región del armazón, no cada banda (R5.7). */
    <div data-update={update.state} className="flex items-center gap-3 border-b border-border bg-muted px-4 py-2">
      <p className="min-w-0 flex-1 text-ui text-pretty text-muted-foreground">
        {waiting ? t("update.waiting", { version }) : t("update.ready", { version })}
      </p>
      {busy ? <p className="shrink-0 text-xs text-muted-foreground">{t("update.busy")}</p> : null}
      <Button
        size="sm"
        variant="outline"
        disabled={waiting}
        onClick={() => {
          // R6.3: si hay trabajo vivo, el puente contesta `busy` y se dice. Un
          // botón que no hace nada y no explica por qué es peor que no tenerlo.
          void bridge.updateInstall().then((res) => setBusy(res.error === "busy"));
        }}
      >
        {t("update.install")}
      </Button>
    </div>
  );
}
