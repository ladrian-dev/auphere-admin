"use client";

/**
 * Copiar, editar y reintentar — spec 013, Requisito 5.
 *
 * **Lo que se copia es el original, no lo pintado.** Con Markdown de por medio
 * son dos cosas distintas: una lista pintada pierde los guiones y una tabla
 * pierde las tuberías, así que copiar el DOM daría algo que ya no es lo que
 * había. Por eso el texto viaja como propiedad y no se lee de la pantalla.
 *
 * **Lo que no se puede hacer, no se pinta.** Un botón que falla al pulsarlo
 * parece roto; uno ausente con su motivo al lado es una pantalla honesta (§V).
 * Copiar es la excepción y se queda siempre: no cambia nada, y bloquearlo
 * sería castigar sin motivo.
 */
import { Check, Copy, Pencil, RotateCcw } from "lucide-react";
import * as React from "react";

export type BlockedReason = "turno_en_marcha" | "decision_pendiente";

export type MessageActionsProps = {
  /** El texto **tal como se escribió**. Nunca el renderizado. */
  text: string;
  canEdit: boolean;
  canRetry: boolean;
  blockedReason?: BlockedReason;
  onEdit?: (text: string) => void;
  onRetry?: () => void;
};

const POR_QUE: Record<BlockedReason, string> = {
  turno_en_marcha: "Hay un turno en marcha: espera a que termine o páralo.",
  decision_pendiente: "Decide la confirmación pendiente antes de seguir.",
};

/** 24×24 como mínimo (WCAG 2.2, 2.5.8), con su foco visible. */
const BOTON =
  "inline-flex min-h-6 min-w-6 items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

export function MessageActions({
  text,
  canEdit,
  canRetry,
  blockedReason,
  onEdit,
  onRetry,
}: MessageActionsProps) {
  const [copiado, setCopiado] = React.useState(false);

  return (
    <div className="flex flex-wrap items-center gap-1">
      <button
        type="button"
        className={BOTON}
        onClick={() => {
          void navigator.clipboard?.writeText(text);
          setCopiado(true);
          window.setTimeout(() => setCopiado(false), 1500);
        }}
      >
        {copiado ? <Check aria-hidden="true" className="size-3" /> : <Copy aria-hidden="true" className="size-3" />}
        {copiado ? "Copiado" : "Copiar"}
      </button>

      {canEdit ? (
        <button type="button" className={BOTON} onClick={() => onEdit?.(text)}>
          <Pencil aria-hidden="true" className="size-3" />
          Editar
        </button>
      ) : null}

      {canRetry ? (
        <button type="button" className={BOTON} onClick={() => onRetry?.()}>
          <RotateCcw aria-hidden="true" className="size-3" />
          Reintentar
        </button>
      ) : null}

      {blockedReason && !canEdit && !canRetry ? (
        <span className="text-xs text-pretty text-muted-foreground">{POR_QUE[blockedReason]}</span>
      ) : null}
    </div>
  );
}
