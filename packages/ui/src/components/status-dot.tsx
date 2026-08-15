import { cn } from "../lib/utils";

type DotTone = "positive" | "warning" | "danger" | "info" | "muted";

const TONE: Record<DotTone, string> = {
  positive: "bg-status-positive",
  warning: "bg-status-warning",
  danger: "bg-status-danger",
  info: "bg-status-info",
  muted: "bg-muted-foreground/40",
};

const HALO: Record<DotTone, string> = {
  positive: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-positive)_18%,transparent)]",
  warning: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-warning)_18%,transparent)]",
  danger: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-danger)_18%,transparent)]",
  info: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-info)_18%,transparent)]",
  muted: "",
};

type StatusDotProps = {
  tone?: DotTone;
  /** Animate — only for live/"happening now" states. */
  pulse?: boolean;
  className?: string;
  /** Screen-reader label; the dot itself is decorative. */
  label?: string;
};

function StatusDot({ tone = "muted", pulse = false, className, label }: StatusDotProps) {
  return (
    <span
      data-slot="status-dot"
      data-tone={tone}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        TONE[tone],
        HALO[tone],
        pulse && "animate-pulse",
        className,
      )}
    />
  );
}

export { StatusDot, type DotTone, type StatusDotProps };
