/**
 * En qué punto está el turno — spec 010, Requisitos 4.3, 4.4 y 4.8.
 *
 * Una línea, encima del compositor, que dice lo que está pasando ahora mismo.
 * Tres decisiones:
 *
 * * **nombra la herramienta** en vez de decir «trabajando»: saber que está
 *   leyendo tu calendario y saber que «está ocupado» son dos informaciones
 *   distintas, y solo la primera deja decidir si esperar;
 * * **no deja cartel puesto al terminar** — la respuesta es el anuncio, y un
 *   «listo» permanente es ruido que se aprende a ignorar (§V);
 * * **se anuncia `polite`**: el único `assertive` del hilo es la petición de
 *   confirmación, y multiplicarlos es cómo se acaba apagando el lector.
 */
import { announces, type TurnState } from "../../turn-state";
import { type AppKey, useAppT } from "../i18n";

export function TurnStatus({ state, tool }: { state: TurnState | null; tool: string | null }) {
  const t = useAppT();
  if (!announces(state)) return null;

  const texto =
    state === "herramienta" && tool
      ? t("turn.herramienta", { tool })
      : t(`turn.${state === "herramienta" ? "herramienta.sinNombre" : state}` as AppKey);

  return (
    <p
      role="status"
      data-turn-state={state}
      className="flex items-center gap-2 border-t border-border px-4 py-2 text-xs text-pretty text-muted-foreground"
    >
      {/* Sin texto alternativo: el punto no añade nada a la frase. Se queda
          quieto con `prefers-reduced-motion`, que es el caso en el que un
          latido constante en el borde de la pantalla molesta de verdad. */}
      <span aria-hidden="true" className="size-2 shrink-0 rounded-full bg-current motion-safe:animate-pulse" />
      <span className="min-w-0">{texto}</span>
    </p>
  );
}
