import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Button } from "./button";
import { StatusDot } from "./status-dot";

type DraftBarState = "pending" | "publishing" | "failed";

/** Todo el texto lo pone el consumidor: el i18n vive en la consola. */
type DraftBarLabels = {
  /** «Cambios sin publicar en» — el bloque añade las pantallas. */
  unpublishedIn: string;
  /** La conjunción con la que se enumeran las pantallas: «y». */
  and: string;
  diff: string;
  publish: string;
  publishing: string;
  retry: string;
  /** Qué roles pueden publicar, para quien no puede. */
  whoCanPublish: ReactNode;
  /** La frase que oye un lector de pantalla cuando hay borrador. */
  announce: string;
  /** La que oye cuando falla la publicación. */
  failureAnnounce?: string;
};

type DraftBarProps = {
  /** Las pantallas de la ficha que difieren de la versión activa. */
  screens: string[];
  canPublish: boolean;
  labels: DraftBarLabels;
  state?: DraftBarState;
  /** Quién dejó los cambios y cuánto hace: un borrador tiene autor. */
  author?: string;
  age?: string;
  /** El botón de publicar como acción principal de la vista. */
  primary?: boolean;
  /** En una pantalla estrecha la barra se ancla abajo. */
  placement?: "inline" | "bottom";
  /** Qué pasó y cómo salir de ello, cuando `state` es `failed`. */
  failure?: ReactNode;
  onDiff?: () => void;
  onPublish?: () => void;
  className?: string;
};

/** «Ajustes y Capacidades»; «Ajustes, Capacidades y Conocimiento». */
function joinScreens(screens: string[], and: string): string {
  if (screens.length <= 1) return screens[0] ?? "";
  return `${screens.slice(0, -1).join(", ")} ${and} ${screens[screens.length - 1]}`;
}

/**
 * El borrador sin publicar, visible desde cualquier pestaña de la ficha
 * (spec 017, R3). Antes solo se veía en «Agente», así que un cambio hecho en
 * Ajustes se quedaba sin publicar sin que nadie lo supiera.
 *
 * Los anuncios viven en dos regiones fijas y separadas — una `status` y una
 * `alert` — porque intercambiar el `role` de un nodo ya montado, o marcarlo
 * `aria-busy` mientras habla, es exactamente cómo se pierde un anuncio.
 */
function DraftBar({
  screens,
  canPublish,
  labels,
  state = "pending",
  author,
  age,
  primary = true,
  placement = "inline",
  failure,
  onDiff,
  onPublish,
  className,
}: DraftBarProps) {
  const failed = state === "failed";
  const publishing = state === "publishing";
  const byline = [author, age].filter(Boolean).join(", ");

  return (
    <div className="flex flex-col gap-2">
      <p className="sr-only" role="status">
        {publishing ? labels.publishing : state === "pending" ? labels.announce : ""}
      </p>
      <p className="sr-only" role="alert">
        {failed ? (labels.failureAnnounce ?? "") : ""}
      </p>
      <div
        data-slot="draft-bar"
        data-testid="draft-bar"
        data-state={state}
        data-placement={placement}
        className={cn(
          "flex flex-col gap-2 rounded-md border px-3 py-2 text-sm",
          failed ? "border-status-danger-border bg-status-danger-bg" : "border-status-info-border bg-status-info-bg",
          className,
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-2">
            <StatusDot tone={failed ? "danger" : "info"} pulse={publishing} />
            <span>
              {publishing ? (
                labels.publishing
              ) : (
                <>
                  {labels.unpublishedIn} <strong>{joinScreens(screens, labels.and)}</strong>
                  {byline ? ` · ${byline}` : ""}
                  {canPublish ? null : <> · {labels.whoCanPublish}</>}
                </>
              )}
            </span>
          </span>
          <span className="flex gap-2">
            {/* Leer lo que cambia nunca depende del permiso de escritura. */}
            {canPublish && !failed ? null : (
              <Button size="sm" variant={canPublish ? "outline" : "ghost"} onClick={onDiff} aria-haspopup="dialog">
                {labels.diff}
              </Button>
            )}
            {canPublish ? (
              <Button size="sm" variant={primary ? "default" : "outline"} onClick={onPublish} loading={publishing} aria-haspopup={failed ? undefined : "dialog"}>
                {failed ? labels.retry : labels.publish}
              </Button>
            ) : null}
          </span>
        </div>
        {failed && failure ? <div className="max-w-prose text-xs text-pretty">{failure}</div> : null}
      </div>
    </div>
  );
}

export { DraftBar, type DraftBarLabels, type DraftBarProps, type DraftBarState };
