import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "../lib/utils";
import { StatusDot, type DotTone } from "./status-dot";

const statusBadgeVariants = cva(
  "inline-flex h-6 w-fit max-w-full shrink-0 items-center gap-2 rounded-full border px-2 text-xs font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        positive: "border-status-positive/30 bg-status-positive/10 text-foreground",
        warning: "border-status-warning/30 bg-status-warning/10 text-foreground",
        danger: "border-status-danger/30 bg-status-danger/10 text-foreground",
        info: "border-status-info/30 bg-status-info/10 text-foreground",
        muted: "border-border bg-muted text-muted-foreground",
      },
    },
    defaultVariants: { tone: "muted" },
  },
);

type StatusBadgeProps = ComponentProps<"span"> &
  VariantProps<typeof statusBadgeVariants> & {
    /** Show the dot (default) — turn off for pure category chips. */
    dot?: boolean;
    pulse?: boolean;
  };

/**
 * A state, named. Tone is one of the four status colours; the label is
 * translated by the caller. Never a bare "active" in plain text.
 */
function StatusBadge({ className, tone = "muted", dot = true, pulse, children, ...props }: StatusBadgeProps) {
  return (
    <span data-slot="status-badge" data-tone={tone} className={cn(statusBadgeVariants({ tone }), className)} {...props}>
      {dot ? <StatusDot tone={(tone ?? "muted") as DotTone} pulse={pulse} /> : null}
      <span className="min-w-0 truncate">{children}</span>
    </span>
  );
}

export { StatusBadge, statusBadgeVariants, type StatusBadgeProps };
