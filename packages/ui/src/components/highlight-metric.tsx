import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Sparkline } from "./sparkline";

type HighlightMetricProps = {
  label: ReactNode;
  /** Already formatted (Intl). */
  value: ReactNode;
  /** One line under the value: the change, what it means. */
  hint?: ReactNode;
  /** Change against the previous period, already formatted. */
  delta?: { label: ReactNode; srLabel?: string };
  trend?: { values: number[]; ariaLabel: string };
  /** Decorative icon before the label, as in ``Metric``. */
  icon?: ReactNode;
  href?: string;
  className?: string;
};

/**
 * The one figure that has to stand out on a screen (spec 026, style G).
 * Same rule and colours as ``Section tone="spotlight"``: dark green in light
 * mode, pistachio in dark. Two on a screen and neither stands out, so it is
 * a hierarchy, not a decoration. Same anatomy and type scale as a ``Metric``
 * with an icon, so it sits in the same grid without breaking it.
 */
function HighlightMetric({ label, value, hint, delta, trend, icon, href, className }: HighlightMetricProps) {
  const body = (
    <>
      <div className="flex min-w-0 items-center gap-2">
        {icon ? (
          <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-md bg-pistachio/20 text-pistachio dark:bg-dark-green/15 dark:text-dark-green [&_svg]:size-4">
            {icon}
          </span>
        ) : null}
        <p className="min-w-0 truncate text-sm font-medium">{label}</p>
      </div>
      <div className="mt-1 flex min-w-0 items-baseline gap-2">
        <p className="min-w-0 truncate text-2xl font-semibold tabular-nums">{value}</p>
        {delta ? (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-pistachio/20 px-2 text-xs font-medium tabular-nums dark:bg-dark-green/15 [&_svg]:size-3" data-slot="highlight-delta">
            <span aria-hidden={delta.srLabel ? true : undefined} className="inline-flex items-center gap-1">
              {delta.label}
            </span>
            {delta.srLabel ? <span className="sr-only">{delta.srLabel}</span> : null}
          </span>
        ) : null}
      </div>
      {hint ? <p className="line-clamp-2 min-w-0 text-sm text-pretty text-pistachio dark:text-dark-green/80">{hint}</p> : null}
      {trend ? <Sparkline values={trend.values} ariaLabel={trend.ariaLabel} className="mt-auto pt-2 text-pistachio dark:text-dark-green" /> : null}
    </>
  );
  const classes = cn(
    "flex min-w-0 flex-col gap-1 rounded-md bg-dark-green p-4 text-anti-flash dark:bg-pistachio dark:text-dark-green",
    href && "transition-opacity hover:opacity-95 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
    className,
  );
  return href ? (
    <a data-slot="highlight-metric" href={href} className={classes}>
      {body}
    </a>
  ) : (
    <div data-slot="highlight-metric" className={classes}>
      {body}
    </div>
  );
}

export { HighlightMetric, type HighlightMetricProps };
