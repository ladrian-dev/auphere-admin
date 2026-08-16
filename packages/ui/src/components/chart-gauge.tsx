import { cn } from "../lib/utils";

type CapGaugeProps = {
  /** Consumed units (already a number; formatted by the caller for the label). */
  value: number;
  /** The cap; ``null`` renders the "no cap" state. */
  max: number | null;
  /** Formatted texts: "1 204 / 5 000", "24 %", "Sin tope". */
  valueLabel: string;
  percentLabel?: string;
  noCapLabel: string;
  label: string;
  className?: string;
};

/**
 * Cap gauge — a linear meter that changes tone at 80 % (warning) and 100 %
 * (danger), mirroring the alert thresholds of CP-24. A native ``<progress>``
 * styled through Tailwind pseudo-element utilities — no inline styles, no
 * chart library.
 */
function CapGauge({ value, max, valueLabel, percentLabel, noCapLabel, label, className }: CapGaugeProps) {
  const percent = max && max > 0 ? Math.min(100, (value / max) * 100) : null;
  const tone = percent == null ? "muted" : percent >= 100 ? "danger" : percent >= 80 ? "warning" : "positive";
  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)} data-slot="chart-gauge">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-xs tracking-eyebrow text-muted-foreground uppercase">{label}</span>
        <span className="min-w-0 truncate text-sm tabular-nums" title={valueLabel}>
          {valueLabel}
          {percentLabel ? <span className="ml-2 text-muted-foreground">{percentLabel}</span> : null}
        </span>
      </div>
      {percent == null ? (
        <p className="text-sm text-muted-foreground">{noCapLabel}</p>
      ) : (
        <progress
          aria-label={label}
          value={Math.round(percent)}
          max={100}
          data-tone={tone}
          className={cn(
            "h-2 w-full appearance-none overflow-hidden rounded-full bg-muted",
            "[&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-bar]:rounded-full",
            "[&::-webkit-progress-value]:rounded-full [&::-moz-progress-bar]:rounded-full",
            tone === "positive" && "[&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary",
            tone === "warning" && "[&::-webkit-progress-value]:bg-status-warning [&::-moz-progress-bar]:bg-status-warning",
            tone === "danger" && "[&::-webkit-progress-value]:bg-status-danger [&::-moz-progress-bar]:bg-status-danger",
          )}
        >
          {percentLabel ?? valueLabel}
        </progress>
      )}
    </div>
  );
}

export { CapGauge, type CapGaugeProps };
