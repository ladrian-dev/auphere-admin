"use client";

import { useT } from "@/i18n/client";

/**
 * Spec 065 (T062; requisitos 5.3 y 6.1): bajo la respuesta del agente, en el chat
 * de prueba y en la conversación de una prueba, con qué modelo respondió, con su
 * nombre o, si no lo tiene, con su id. Si respondió la reserva, se dice también.
 * Discreto, sin `role`: las dos listas ya se leen enteras, y el chat es una región
 * viva que lo diría dos veces. Sin modelo (conversaciones de antes), nada.
 *
 * La API dice qué modelo respondió y si fue la reserva, no por qué ni cuál falló:
 * no se nombra el elegido, que pudo cambiar después de la conversación.
 */
export function AnsweredBy({ model, name, fellBack }: { model?: string | null; name?: string | null; fellBack?: boolean }) {
  const t = useT();
  if (!model) return null;
  const shown = name || model;
  return (
    <p className="max-w-full min-w-0 px-1 text-xs text-pretty wrap-anywhere text-muted-foreground" data-slot="answered-by">
      {fellBack ? t("agentModel.answeredReserve", { model: shown }) : t("agentModel.answered", { model: shown })}
    </p>
  );
}
