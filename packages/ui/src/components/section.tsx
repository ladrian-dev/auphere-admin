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
   * `spotlight`: fondo verde oscuro de marca, para el **único** panel que
   * tiene que destacar sobre los demás de la pantalla. Dos a la vista y
   * ninguno destaca, así que no es un tono decorativo: es una jerarquía.
   * La descripción y los detalles pasan a pistacho, que da 9:1 sobre ese
   * fondo; el texto secundario en gris se perdería.
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
        tone === "spotlight" && "bg-dark-green text-anti-flash ring-0",
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
              <p className={cn("text-sm text-pretty", tone === "spotlight" ? "text-pistachio" : "text-muted-foreground")}>
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
