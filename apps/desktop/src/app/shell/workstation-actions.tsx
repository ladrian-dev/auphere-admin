/**
 * Lo que se puede hacer con la máquina — spec 010, Requisitos 8.2 a 8.5.
 *
 * Con la barra de 44 px retirada, estas tres cosas son **diálogos de la
 * aplicación**: emparejar, declarar directorios y desemparejar. Antes vivían en
 * hojas que caían fuera de una ventana con `overflow: hidden`, o en el diálogo
 * nativo del navegador.
 *
 * Qué se ofrece lo decide `WorkstationView.actions`, que sale del mismo sitio
 * que el estado: una acción que no aplica **no se pinta**, en vez de pintarse
 * apagada esperando un clic que dará un «ahora no» (§V).
 */
import { Button } from "@nexus/ui";

import type { WorkstationView } from "../bridge";
import { type AppKey, useAppT } from "../i18n";

export type WorkstationAction = "introducir_codigo" | "directorios" | "desemparejar" | "actualizar";

export function WorkstationActions({
  state,
  onAction,
}: {
  state: WorkstationView | null;
  onAction: (action: WorkstationAction) => void;
}) {
  const t = useAppT();
  if (!state || state.actions.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {state.actions.map((action) => (
        <Button key={action} size="sm" variant="outline" onClick={() => onAction(action as WorkstationAction)}>
          {t(`workstation.action.${action}` as AppKey)}
        </Button>
      ))}
    </div>
  );
}
