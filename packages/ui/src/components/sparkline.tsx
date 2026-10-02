import { cn } from "../lib/utils";

type SparklineProps = {
  /** One value per point, oldest first. Fewer than two points draws nothing. */
  values: number[];
  /** Screen-reader description, e.g. «Conversaciones de los últimos 7 días». */
  ariaLabel: string;
  className?: string;
};

/**
 * A tiny trend line for a figure (spec 026). No axes, no tooltip: the
 * figure next to it carries the number, the line only says «going up or
 * down». Colour is ``currentColor`` so the caller picks the tone with a
 * text token; the area under the line is the same colour, faint.
 */
function Sparkline({ values, ariaLabel, className }: SparklineProps) {
  if (values.length < 2) return null;
  const width = 100;
  const height = 32;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values.map((v, i) => {
    const x = i * step;
    const y = max === min ? height / 2 : height - 2 - ((v - min) / span) * (height - 4);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const area = `0,${height} ${points.join(" ")} ${width},${height}`;
  return (
    <svg
      data-slot="sparkline"
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn("h-8 w-full text-primary", className)}
    >
      <polygon points={area} fill="currentColor" opacity={0.12} />
      <polyline points={points.join(" ")} fill="none" stroke="currentColor" strokeWidth={1.5} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export { Sparkline, type SparklineProps };
