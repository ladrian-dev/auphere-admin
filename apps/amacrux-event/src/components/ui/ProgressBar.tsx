export interface ProgressBarProps {
  value: number; // 0–100
  label: string;
  detail?: string;
}

export function ProgressBar({ value, label, detail }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="w-full">
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs font-medium text-ink-muted">
        <span>{label}</span>
        {detail ? <span>{detail}</span> : null}
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
        aria-label={label}
        className="h-2 w-full overflow-hidden rounded-full bg-line"
      >
        <div className="h-full rounded-full bg-accent transition-[width] duration-(--duration-base) ease-(--ease-out)" style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}
