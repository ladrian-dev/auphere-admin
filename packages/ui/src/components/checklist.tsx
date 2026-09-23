import { AlertTriangle, Check, CircleDashed, Loader2, MinusCircle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Button } from "./button";

type ChecklistStatus = "todo" | "current" | "running" | "done" | "failed" | "skipped";

type ChecklistItem = {
  key: string;
  label: ReactNode;
  status: ChecklistStatus;
  /** Where the step is done; rendered through ``renderLink`` so the app can use its router. */
  href?: string;
  /** One line under the label: what happened, or what is missing. */
  detail?: ReactNode;
  onRetry?: () => void;
  retryLabel?: ReactNode;
};

type ChecklistProps = {
  items: ChecklistItem[];
  /** The name of the list for assistive tech («Primeros pasos»). */
  ariaLabel: string;
  /** How to render a link (``next/link``, ``<a>``, …). Default: ``<a>``. */
  renderLink?: (item: ChecklistItem, children: ReactNode, className: string) => ReactNode;
  dense?: boolean;
  className?: string;
};

function Icon({ status }: { status: ChecklistStatus }) {
  const cls = "size-4 shrink-0";
  switch (status) {
    case "done":
      return <Check className={cn(cls, "text-status-positive-text")} aria-hidden="true" />;
    case "running":
      return <Loader2 className={cn(cls, "animate-spin text-status-info-text")} aria-hidden="true" />;
    case "failed":
      return <AlertTriangle className={cn(cls, "text-destructive")} aria-hidden="true" />;
    case "skipped":
      return <MinusCircle className={cn(cls, "text-muted-foreground")} aria-hidden="true" />;
    case "current":
      return <CircleDashed className={cn(cls, "text-foreground")} aria-hidden="true" />;
    default:
      return <CircleDashed className={cn(cls, "text-muted-foreground")} aria-hidden="true" />;
  }
}

/**
 * Steps with a real per-step state (Bloque C): the onboarding, the workstation
 * setup, the stages of the client wizard. Six states, one icon each; a failed
 * step carries its reason and its retry; a pending step with an ``href`` is
 * the link to where it gets done. Presentational: the state machine stays
 * in the caller.
 */
function Checklist({ items, ariaLabel, renderLink, dense, className }: ChecklistProps) {
  const link = renderLink ?? ((item, children, cls) => (
    <a href={item.href} className={cls}>
      {children}
    </a>
  ));
  return (
    <ol data-slot="checklist" aria-label={ariaLabel} className={cn("flex flex-col", dense ? "gap-0" : "gap-1", className)}>
      {items.map((item) => {
        const done = item.status === "done";
        const skipped = item.status === "skipped";
        const inner = (
          <>
            <Icon status={item.status} />
            <span className={cn("min-w-0 flex-1 text-pretty", (done || skipped) && "text-muted-foreground", done && "line-through")}>{item.label}</span>
          </>
        );
        const rowCls = "flex min-w-0 items-center gap-2 rounded-sm px-1 py-1 text-sm";
        const actionable = item.href && (item.status === "todo" || item.status === "current");
        return (
          <li key={item.key} data-status={item.status} aria-current={item.status === "current" ? "step" : undefined} className="flex min-w-0 flex-col">
            {actionable ? link(item, inner, cn(rowCls, "hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50")) : <span className={rowCls}>{inner}</span>}
            {item.detail || (item.status === "failed" && item.onRetry) ? (
              <div className="flex flex-wrap items-center gap-2 pl-7 pb-1">
                {item.detail ? (
                  <span role={item.status === "failed" ? "alert" : undefined} className={cn("min-w-0 text-xs text-pretty", item.status === "failed" ? "text-destructive" : "text-muted-foreground")}>
                    {item.detail}
                  </span>
                ) : null}
                {item.status === "failed" && item.onRetry ? (
                  <Button type="button" size="xs" variant="outline" onClick={item.onRetry}>
                    {item.retryLabel}
                  </Button>
                ) : null}
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export { Checklist, type ChecklistItem, type ChecklistProps, type ChecklistStatus };
