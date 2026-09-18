/**
 * Desemparejar — spec 010, Requisito 8.5.
 *
 * La barra lo confirmaba con `confirm()`, el diálogo **nativo del navegador**:
 * no se puede vestir, no dice en qué aplicación estás, y en Electron aparece
 * como una alerta de sistema sin contexto encima de una barra de 44 px.
 *
 * Lo que este diálogo dice y aquél no: **qué deja de funcionar y qué no**.
 * Nombrar sólo la pérdida hace que desemparejar parezca borrar el trabajo; los
 * hilos, las tareas y el historial siguen donde estaban, porque viven en el
 * servidor. Lo que se olvida es la credencial de esta máquina.
 *
 * Y el botón por defecto es cancelar: salir por costumbre no puede dejar a
 * alguien sin máquina.
 */
import { useEffect, useRef, useState } from "react";

import { Button } from "@nexus/ui";

import { bridge } from "../bridge";
import { useAppT } from "../i18n";

export function UnpairDialog({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const t = useAppT();
  const [sending, setSending] = useState(false);
  const cancel = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancel.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="unpair-title"
      className="m-auto flex w-full max-w-prose flex-col gap-4 rounded-md border border-border bg-card p-6"
    >
      <h2 id="unpair-title" className="text-base font-semibold text-balance">
        {t("unpair.title")}
      </h2>
      <p className="text-ui text-pretty">{t("unpair.loses")}</p>
      <p className="text-ui text-pretty text-muted-foreground">{t("unpair.keeps")}</p>
      <div className="flex flex-wrap gap-2">
        {/* El primero y el que recibe el foco: salir por costumbre no puede
            dejar a alguien sin máquina. */}
        <Button ref={cancel} size="sm" variant="outline" onClick={onClose}>
          {t("unpair.cancel")}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={sending}
          onClick={() => {
            setSending(true);
            void bridge.workstationUnpair().then(() => {
              setSending(false);
              onDone();
            });
          }}
        >
          {t("unpair.confirm")}
        </Button>
      </div>
    </div>
  );
}
