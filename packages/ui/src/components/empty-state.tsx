import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/utils";

type EmptyStateProps = {
  icon?: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  /** The action that gets the user out of the empty state. Required by
   *  the 5-states rule unless ``readonly`` is set (analyst views). */
  action?: ReactNode;
  readonly?: boolean;
  className?: string;
};

/**
 * "Empty with an action" (Scott Hurff). Dashed frame, centred, one clear
 * next step. Used inside tables (as a full-width row), cards and pages.
 */
function EmptyState({ icon: Icon, title, description, action, readonly, className }: EmptyStateProps) {
  return (
    <div
      data-slot="empty-state"
      role="status"
      className={cn(
        "flex min-w-0 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-card px-6 py-16 text-center",
        className,
      )}
    >
      {Icon ? (
        <span className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
          <Icon className="size-5" aria-hidden="true" />
        </span>
      ) : null}
      <p className="text-sm font-medium text-balance">{title}</p>
      {description ? (
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
      {!action && !readonly && process.env.NODE_ENV !== "production" ? (
        <p className="text-xs text-status-warning">EmptyState without action — pass one or set readonly.</p>
      ) : null}
    </div>
  );
}

export { EmptyState, type EmptyStateProps };
