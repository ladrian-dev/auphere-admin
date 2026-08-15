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
  /** Optional breadcrumb / context line rendered above the eyebrow. */
  context?: ReactNode;
  className?: string;
};

/**
 * The one PageHeader. Title is an ``h1``; long titles wrap and balance,
 * they never overflow (``min-w-0`` + ``text-balance``).
 */
function PageHeader({ eyebrow, title, description, actions, context, className }: PageHeaderProps) {
  return (
    <header
      data-slot="page-header"
      className={cn(
        "flex min-w-0 flex-col gap-3 border-b border-border pb-6 md:flex-row md:items-end md:justify-between",
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-2">
        {context ? <div className="min-w-0 text-sm text-muted-foreground">{context}</div> : null}
        {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
        <h1 className="min-w-0 text-2xl font-semibold text-balance md:text-3xl">{title}</h1>
        {description ? (
          <p className="max-w-prose text-base text-pretty text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2 md:justify-end">{actions}</div>
      ) : null}
    </header>
  );
}

export { PageHeader, type PageHeaderProps };
