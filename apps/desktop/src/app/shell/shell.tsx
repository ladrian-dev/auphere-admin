/**
 * El armazón — spec 010, Requisitos 1.1, 1.2 y 1.3.
 *
 * Esta vista ocupa **toda la ventana** y es la dueña del marco: la franja
 * superior con los controles del sistema integrados, la lista lateral y el
 * panel de contenido. La consola se pinta **dentro del panel**, como una vista
 * que el proceso principal coloca encima; por eso el armazón le dice dónde
 * cabe, midiendo el hueco real en vez de calcularlo con constantes que
 * envejecerían aparte.
 *
 * El invariante que el spike de la Fase 0 confirmó: la consola nunca se solapa
 * con la franja. Aquí se cumple por construcción —el panel empieza donde
 * termina la franja— y el proceso principal lo vuelve a acotar por su cuenta.
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { bridge } from "../bridge";
import { Strip } from "./strip";

export type ShellProps = {
  /** El objeto en el que se está. Nunca «Auphere» (HIG: el título es útil). */
  title: string;
  sidebar: ReactNode;
  /** Lo que se pinta en el panel. Vacío cuando ahí va la consola. */
  children?: ReactNode;
  onSearch: () => void;
  status?: ReactNode;
  /**
   * Cuando la sección activa la pinta la consola, el panel se deja **libre**:
   * la vista de la consola lo ocupa. Sin esto se verían las dos cosas.
   */
  panelBelongsToConsole: boolean;
  sidebarWidth: number;
  onSidebarWidth: (width: number) => void;
};

/** Límites de la lista lateral; los mismos que aplica el proceso principal. */
const MIN = 220;
const MAX = 320;

export function Shell({
  title,
  sidebar,
  children,
  onSearch,
  status,
  panelBelongsToConsole,
  sidebarWidth,
  onSidebarWidth,
}: ShellProps) {
  const panel = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  /**
   * Dónde cabe la consola. Se **mide**, no se calcula: lo que el proceso
   * principal necesita es el rectángulo de verdad, con la lista lateral en la
   * anchura que tenga ahora mismo.
   */
  const report = useCallback(() => {
    const element = panel.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    void bridge.shellContentBounds({
      x: Math.round(rect.left),
      y: Math.round(rect.top),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    });
  }, []);

  useEffect(() => {
    report();
    const observer = new ResizeObserver(report);
    if (panel.current) observer.observe(panel.current);
    window.addEventListener("resize", report);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", report);
    };
  }, [report]);

  // Arrastrar el borde de la lista lateral. Se escucha en la ventana para que
  // el puntero pueda salirse del borde sin perder el arrastre.
  useEffect(() => {
    if (!dragging) return;
    const move = (event: MouseEvent) => onSidebarWidth(Math.min(MAX, Math.max(MIN, Math.round(event.clientX))));
    const stop = () => setDragging(false);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", stop);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", stop);
    };
  }, [dragging, onSidebarWidth]);

  return (
    <div className="flex h-dvh min-h-0 flex-col bg-background text-foreground">
      <Strip title={title} onSearch={onSearch} status={status} />

      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 shrink-0" style={{ width: sidebarWidth }}>
          {sidebar}
        </div>

        {/* El tirador del borde. Es un separador, y como tal se puede mover
            también con el teclado: WCAG 2.1.1 no admite «sólo con ratón». */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-valuenow={sidebarWidth}
          aria-valuemin={MIN}
          aria-valuemax={MAX}
          tabIndex={0}
          onMouseDown={() => setDragging(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") onSidebarWidth(Math.max(MIN, sidebarWidth - 16));
            if (event.key === "ArrowRight") onSidebarWidth(Math.min(MAX, sidebarWidth + 16));
          }}
          className="w-1 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-border"
        />

        <div ref={panel} className="min-h-0 min-w-0 flex-1">
          {/* Con la consola delante no se pinta nada aquí: ese hueco es suyo. */}
          {panelBelongsToConsole ? null : children}
        </div>
      </div>
    </div>
  );
}
