import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Button } from "./button";

type ErrorStateProps = {
  title: ReactNode;
  /** Human message. Never a stack trace; the digest goes to logs. */
  description?: ReactNode;
  /** Retry handler → renders the button. */
  onRetry?: () => void;
  retryLabel?: ReactNode;
  className?: string;
};

/**
 * "Error with retry". Same frame as EmptyState so the eye reads both as
 * "nothing to show here, and here is what to do".
 */
function ErrorState({ title, description, onRetry, retryLabel = "Retry", className }: ErrorStateProps) {
  return (
    <div
      data-slot="error-state"
      role="alert"
      className={cn(
        "flex min-w-0 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-status-danger/40 bg-card px-6 py-16 text-center",
        className,
      )}
    >
      <span className="grid size-10 place-items-center rounded-full bg-status-danger/10 text-status-danger">
        <AlertTriangle className="size-5" aria-hidden="true" />
      </span>
      <p className="text-sm font-medium text-balance">{title}</p>
      {description ? (
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{description}</p>
      ) : null}
      {onRetry ? (
        <Button className="mt-2" variant="outline" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}

export { ErrorState, type ErrorStateProps };
