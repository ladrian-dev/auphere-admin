/**
 * La franja superior — spec 010, Requisito 1.1.
 *
 * Es **la única región de arrastre de la ventana**, y eso no es un detalle de
 * estilo: el spike de la Fase 0 demostró que arrastrar funciona con la consola
 * pintada encima del panel precisamente porque no hay solape de regiones. Si
 * otra vista o otro elemento declarara `drag`, la ventana dejaría de moverse
 * por sitios que parecen arrastrables (electron#43320).
 *
 * Dentro de una región de arrastre **los eventos de puntero no llegan**, así
 * que todo lo que se pulse aquí va envuelto en `no-drag`. Por eso los controles
 * viven en contenedores marcados, y el test lo comprueba control por control.
 */
import type { ReactNode } from "react";

import { useAppT } from "../i18n";

/**
 * El hueco de los semáforos de macOS. El sistema los pinta **encima** de la
 * franja, así que el contenido empieza después: sin esto, el título queda
 * debajo de los botones de la ventana.
 */
const TRAFFIC_LIGHTS = 78;

export function Strip({
  title,
  onSearch,
  status,
}: {
  /** El objeto en el que se está: el teammate o la sección. Nunca «Auphere». */
  title: string;
  onSearch: () => void;
  /** El estado de la máquina, que se ve sin abrir nada. */
  status?: ReactNode;
}) {
  const t = useAppT();

  return (
    <header
      className="drag flex h-13 shrink-0 items-center gap-3 border-b border-border bg-background pr-3"
      style={{ paddingLeft: TRAFFIC_LIGHTS }}
      data-traffic-lights={TRAFFIC_LIGHTS}
    >
      <h1 className="min-w-0 flex-1 truncate text-ui font-medium" title={title}>
        {title}
      </h1>

      {status ? <div className="no-drag flex min-w-0 items-center">{status}</div> : null}

      <div className="no-drag flex shrink-0 items-center">
        <button
          type="button"
          onClick={onSearch}
          aria-keyshortcuts="Meta+K"
          className="flex min-h-6 items-center gap-2 rounded-sm border border-border px-2 text-xs text-muted-foreground transition-colors hover:bg-muted"
        >
          {t("shell.search")}
          <kbd className="font-mono text-xs">⌘K</kbd>
        </button>
      </div>
    </header>
  );
}
