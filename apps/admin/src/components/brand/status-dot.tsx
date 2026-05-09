import { cn } from "@/lib/utils";

type StatusKind = "positive" | "warning" | "danger" | "info" | "muted";

const TONE: Record<StatusKind, string> = {
  positive: "bg-[color:var(--color-status-positive)]",
  warning: "bg-[color:var(--color-status-warning)]",
  danger: "bg-[color:var(--color-status-danger)]",
  info: "bg-[color:var(--color-status-info)]",
  muted: "bg-muted-foreground/40",
};

const HALO: Record<StatusKind, string> = {
  positive: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-positive)_18%,transparent)]",
  warning: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-warning)_18%,transparent)]",
  danger: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-danger)_18%,transparent)]",
  info: "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-info)_18%,transparent)]",
  muted: "",
};

/**
 * Status dot — 6px filled circle with a soft halo. The halo is the
 * brand's only allowed glow (the website's pulse on neural sinapsis);
 * we reuse the pattern at smaller scale to mark health states without
 * resorting to coloured pills, which would feel marketing-flashy.
 */
export function StatusDot({
  tone = "positive",
  pulse = false,
  className,
}: {
  tone?: StatusKind;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block size-1.5 rounded-full",
        TONE[tone],
        HALO[tone],
        pulse && "animate-pulse",
        className,
      )}
    />
  );
}
