import * as React from "react";

import { cn } from "../lib/utils";

type SectionProps = Omit<React.ComponentProps<"section">, "title"> & {
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** Right-aligned controls next to the title. */
  actions?: React.ReactNode;
  headingLevel?: 2 | 3;
  /** Drop the padding for content that manages its own (a table). */
  padded?: boolean;
  /** Plain block: no card surface, just the title + spacing. */
  flat?: boolean;
  /**
   * `spotlight`: el **único** panel que tiene que destacar sobre los demás de
   * la pantalla. Dos a la vista y ninguno destaca, así que no es un tono
   * decorativo: es una jerarquía.
   *
   * **Y se invierte con el tema**, porque lo que destaca no es el color sino
   * el contraste con lo que tiene al lado. En claro es verde oscuro sobre
   * tarjetas claras. En oscuro era verde oscuro sobre fondo oscuro, o sea
   * que se fundía y dejaba de hacer su trabajo (owner, 2026-09-28): ahí pasa
   * a **pistacho**, que sigue siendo verde de marca. Blanco del todo
   * destacaría igual pero rompería la familia de color de la pantalla.
   *
   * El texto acompaña al fondo, no al tema: sobre verde oscuro la descripción
   * va en pistacho —el gris secundario se perdería— y sobre hueso vuelve al
   * verde oscuro.
   */
  tone?: "default" | "spotlight";
};

/**
 * A panel with a title (Bloque C). Replaces the 24 hand-written
 * ``rounded-md bg-card p-4 ring-1`` blocks: one surface, one heading level,
 * ``aria-labelledby`` wired so the region has a name.
 */
function Section({ title, description, actions, headingLevel = 2, padded = true, flat, tone = "default", className, children, id, ...props }: SectionProps) {
  const generated = React.useId();
  const headingId = title ? `${id ?? generated}-title` : undefined;
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section
      data-slot="section"
      id={id}
      aria-labelledby={headingId}
      data-tone={tone}
      className={cn(
        "flex min-w-0 flex-col gap-(--space-stack)",
        !flat && "rounded-md bg-card ring-1 ring-foreground/10",
        !flat && padded && "p-4",
        tone === "spotlight" && "bg-dark-green text-anti-flash ring-0 dark:bg-pistachio dark:text-dark-green",
        className,
      )}
      {...props}
    >
      {title || actions ? (
        <div className={cn("flex min-w-0 flex-wrap items-start justify-between gap-(--space-inline)", !flat && !padded && "px-4 pt-4")}>
          <div className="min-w-0">
            {title ? (
              <Heading id={headingId} className="text-base font-medium text-balance">
                {title}
              </Heading>
            ) : null}
            {description ? (
              <p className={cn("text-sm text-pretty", tone === "spotlight" ? "text-pistachio dark:text-dark-green/80" : "text-muted-foreground")}>
                {description}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export { Section, type SectionProps };
