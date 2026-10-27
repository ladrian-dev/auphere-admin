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
        // `warn` es el nombre del tono en `contracts/events.md` (spec 047): el
        // mismo ámbar que `warning`, para que la consola pinte el código tal
        // como lo manda la API sin traducirlo a mano en cada pantalla.
        warn: "border-status-warning/30 bg-status-warning/10 text-foreground",
        danger: "border-status-danger/30 bg-status-danger/10 text-foreground",
        info: "border-status-info/30 bg-status-info/10 text-foreground",
        muted: "border-border bg-muted text-muted-foreground",
      },
    },
    defaultVariants: { tone: "muted" },
  },
);

type StatusBadgeTone = NonNullable<VariantProps<typeof statusBadgeVariants>["tone"]>;

/** The tones of `contracts/events.md` (spec 047): the five a visible state can take. */
type StateTone = "positive" | "info" | "warn" | "danger" | "muted";

/**
 * Spec 047, `contracts/events.md` §1.3 — the agent's visible state, a code
 * the API derives once (R25.5), and its tone. The text is the caller's.
 */
const AGENT_STATE_TONE = {
  archived: "muted",
  paused: "warn",
  draft: "muted",
  serving: "positive",
  testing: "info",
  ready_no_channel: "info",
} as const satisfies Record<string, StateTone>;

/** Spec 047, `contracts/events.md` §1.2 — the channel's visible state and its tone. */
const CHANNEL_STATE_TONE = {
  pending_link: "info",
  disconnected: "muted",
  problem: "danger",
  paused: "warn",
  unconfigured: "muted",
  team_only: "info",
  everyone: "positive",
} as const satisfies Record<string, StateTone>;

type AgentVisibleState = keyof typeof AGENT_STATE_TONE;
type ChannelVisibleState = keyof typeof CHANNEL_STATE_TONE;

const DOT_TONE: Record<StatusBadgeTone, DotTone> = {
  positive: "positive",
  warning: "warning",
  warn: "warning",
  danger: "danger",
  info: "info",
  muted: "muted",
};

type StatusBadgeProps = ComponentProps<"span"> &
  VariantProps<typeof statusBadgeVariants> & {
    /** Show the dot (default) — turn off for pure category chips. */
    dot?: boolean;
    pulse?: boolean;
  };

/**
 * A state, named. Tone is one of the status colours; the label is translated
 * by the caller. Never a bare "active" in plain text.
 */
function StatusBadge({ className, tone = "muted", dot = true, pulse, children, ...props }: StatusBadgeProps) {
  const resolved: StatusBadgeTone = tone ?? "muted";
  return (
    <span data-slot="status-badge" data-tone={resolved} className={cn(statusBadgeVariants({ tone: resolved }), className)} {...props}>
      {dot ? <StatusDot tone={DOT_TONE[resolved]} pulse={pulse} /> : null}
      <span className="min-w-0 truncate">{children}</span>
    </span>
  );
}

export {
  AGENT_STATE_TONE,
  CHANNEL_STATE_TONE,
  StatusBadge,
  statusBadgeVariants,
  type AgentVisibleState,
  type ChannelVisibleState,
  type StateTone,
  type StatusBadgeProps,
  type StatusBadgeTone,
};
