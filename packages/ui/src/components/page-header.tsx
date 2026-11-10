import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Eyebrow } from "./eyebrow";

type PageHeaderProps = {
  /** Small mono label above the title ("Clientes", "Equipo"). */
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  /** Right-aligned actions (Buttons). Wraps under the title on narrow screens. */
  actions?: ReactNode;
  /** Volver (la consola nueva): un botón redondo que va en la fila del título. */
  back?: ReactNode;
  /** Optional breadcrumb / context line rendered above the eyebrow. */
  context?: ReactNode;
  /** ``compact``: a smaller title and less air, for a dashboard where the
   *  data is the content and the greeting is not (the partner home).
   *  ``display``: the big title of the new partner console (spec 047, the
   *  approved prototype «Consola de partners v2»). */
  size?: "default" | "compact" | "display";
  className?: string;
};

/**
 * The one PageHeader. Title is an ``h1``; long titles wrap and balance,
 * they never overflow (``min-w-0`` + ``text-balance``).
 */
function PageHeader({ eyebrow, title, description, actions, context, back, size = "default", className }: PageHeaderProps) {
  return (
    <header
      data-slot="page-header"
      className={cn(
        "flex min-w-0 flex-col gap-3 border-b border-border md:flex-row md:items-end md:justify-between",
        size === "compact" ? "pb-3" : size === "display" ? "pb-5" : "pb-6",
        className,
      )}
    >
      <div className={cn("flex min-w-0 flex-col", size === "compact" ? "gap-1" : "gap-2")}>
        {context ? <div className="min-w-0 text-sm text-muted-foreground">{context}</div> : null}
        {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
        <div className="flex min-w-0 items-center gap-3">
          {back}
          <h1
            className={cn(
              "min-w-0 font-semibold text-balance",
              size === "compact" ? "text-lg md:text-xl" : size === "display" ? "text-2xl tracking-tighter sm:text-display" : "text-2xl md:text-3xl",
            )}
          >
            {title}
          </h1>
        </div>
        {description ? (
          <p className="text-base text-pretty text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2 md:justify-end">{actions}</div>
      ) : null}
    </header>
  );
}

export { PageHeader, type PageHeaderProps };
