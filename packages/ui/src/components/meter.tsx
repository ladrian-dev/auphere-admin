import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Skeleton } from "./skeleton";

type MeterTone = "positive" | "warning" | "danger" | "info" | "neutral";

type MeterProps = {
  /** Consumed units. Formatted by the caller for the labels; never here. */
  value: number;
  /** The cap. ``null`` renders the «no cap» state instead of a bar. */
  max: number | null;
  /** ``auto`` picks the tone from the thresholds (the CP-24 rule: 80 %
   *  warning, 100 % danger); a fixed tone overrides it. */
  tone?: "auto" | MeterTone;
  thresholds?: { warning: number; danger: number };
  size?: "sm" | "md";
  /** What the meter measures — visible, or screen-reader only with ``labelHidden``. */
  label: ReactNode;
  labelHidden?: boolean;
  /** «1 204 / 5 000 · 24 %». Also the ``aria-valuetext``. */
  valueLabel?: string;
  hint?: ReactNode;
  /** Shown instead of the bar when ``max`` is null. */
  noMaxLabel?: ReactNode;
  loading?: boolean;
  className?: string;
};

function toneFor(percent: number, thresholds: { warning: number; danger: number }): MeterTone {
  if (percent >= thresholds.danger) return "danger";
  if (percent >= thresholds.warning) return "warning";
  return "positive";
}

const FILL: Record<MeterTone, string> = {
  positive: "[&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary",
  warning: "[&::-webkit-progress-value]:bg-status-warning [&::-moz-progress-bar]:bg-status-warning",
  danger: "[&::-webkit-progress-value]:bg-status-danger [&::-moz-progress-bar]:bg-status-danger",
  info: "[&::-webkit-progress-value]:bg-status-info [&::-moz-progress-bar]:bg-status-info",
  neutral: "[&::-webkit-progress-value]:bg-foreground/60 [&::-moz-progress-bar]:bg-foreground/60",
};

/**
 * One meter for every «how much of the cap» in the product (Bloque C): the
 * client's quota, the playground budget, the knowledge cap, the onboarding
 * progress. A native ``<progress>`` — semantics and a11y for free, and the
 * value IS the width, so no inline style — tinted through pseudo-elements.
 */
function Meter({
  value,
  max,
  tone = "auto",
  thresholds = { warning: 80, danger: 100 },
  size = "md",
  label,
  labelHidden,
  valueLabel,
  hint,
  noMaxLabel,
  loading,
  className,
}: MeterProps) {
  const percent = max != null && max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : null;
  const resolved: MeterTone = tone === "auto" ? (percent == null ? "neutral" : toneFor(percent, thresholds)) : tone;
  const height = size === "sm" ? "h-1" : "h-2";
  const labelNode = <span className={cn("text-sm font-medium", labelHidden && "sr-only")}>{label}</span>;
  return (
    <div data-slot="meter" data-tone={resolved} className={cn("flex min-w-0 flex-col gap-(--space-inline)", className)}>
      {labelHidden && !valueLabel ? (
        labelNode
      ) : (
        <div className="flex items-baseline justify-between gap-(--space-inline)">
          {labelNode}
          {valueLabel ? (
            <span className="min-w-0 truncate font-mono text-xs text-muted-foreground tabular-nums" title={valueLabel}>
              {valueLabel}
            </span>
          ) : null}
        </div>
      )}
      {loading ? (
        <Skeleton className={cn(height, "w-full rounded-full")} />
      ) : percent == null ? (
        <p className="text-sm text-muted-foreground">{noMaxLabel}</p>
      ) : (
        <progress
          value={Math.min(value, max as number)}
          max={max as number}
          aria-label={typeof label === "string" ? label : undefined}
          aria-valuetext={valueLabel}
          className={cn(
            height,
            "w-full appearance-none overflow-hidden rounded-full bg-muted",
            "[&::-webkit-progress-bar]:rounded-full [&::-webkit-progress-bar]:bg-muted",
            "[&::-webkit-progress-value]:rounded-full [&::-moz-progress-bar]:rounded-full",
            "[&::-webkit-progress-value]:transition-[width] [&::-webkit-progress-value]:duration-(--duration-state)",
            FILL[resolved],
          )}
        >
          {valueLabel}
        </progress>
      )}
      {hint ? <p className="text-xs text-muted-foreground text-pretty">{hint}</p> : null}
    </div>
  );
}

export { Meter, toneFor as meterToneFor, type MeterProps, type MeterTone };
