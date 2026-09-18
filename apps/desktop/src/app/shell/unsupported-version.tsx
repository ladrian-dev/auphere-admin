/**
 * Esta versión ya no se admite — spec 010, Requisito 6.4.
 *
 * Lo que había: «Esta versión ya no se admite · actualiza para seguir», y
 * «Actualizar» abría **el directorio crudo del canal** en el navegador: una
 * lista de ficheros `.zip` y `.yml`. Las dos mitades fallaban a la vez — no se
 * decía qué versión hace falta, y el destino no era un sitio donde alguien
 * pueda resolver nada.
 *
 * Aquí se nombra la mínima y la instalada —para poder compararlas y para poder
 * contárselo a soporte— y la acción se queda **dentro**: si ya está descargada,
 * se instala; si no, se comprueba el canal. Y si el canal no trae nada, se dice
 * a quién pedirlo, en vez de dejar un botón que se pulsa sin que pase nada.
 */
import { useState } from "react";

import { Button } from "@nexus/ui";

import { bridge, type UpdateView } from "../bridge";
import { useAppT } from "../i18n";

export function UnsupportedVersion({
  required,
  installed,
  update,
}: {
  /** La mínima que admite la plataforma. `null` = no consta; no se inventa. */
  required: string | null;
  installed: string;
  update: UpdateView | null;
}) {
  const t = useAppT();
  const [checked, setChecked] = useState(false);
  const ready = update?.state === "lista";

  return (
    /* Lo anuncia la región del armazón, no cada banda (R5.7). */
    <div className="flex items-center gap-3 border-b border-border bg-muted px-4 py-2">
      <p className="min-w-0 flex-1 text-ui text-pretty text-muted-foreground">
        {required
          ? t("update.unsupported", { required, installed })
          : t("update.unsupported.nomin", { installed })}
        {/* Sólo después de comprobar y no encontrar nada: decirlo antes sería
            desanimar de pulsar lo único que puede arreglarlo. */}
        {checked && !ready ? ` ${t("update.unsupported.nochannel")}` : ""}
      </p>
      <Button
        size="sm"
        onClick={() => {
          if (ready) {
            void bridge.updateInstall();
            return;
          }
          void bridge.updateCheck().then(() => setChecked(true));
        }}
      >
        {ready ? t("update.install") : t("update.check")}
      </Button>
    </div>
  );
}
