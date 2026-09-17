import { RANGE_DESCRIPTIONS, RANGE_LABELS } from "@/domain/copy";
import { SCORE_RANGES, type ScoreRange } from "@/domain/enums";
import { cx } from "@/lib/cx";

export function OpportunityLevel({ level }: { level: ScoreRange }) {
  const idx = SCORE_RANGES.indexOf(level);
  return (
    <div className="rounded-lg border border-line bg-surface p-4 shadow-1">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Nivel de oportunidad</p>
        <p className="font-display text-lg font-bold text-ink">{RANGE_LABELS[level]}</p>
      </div>
      <ol className="mt-3 grid grid-cols-4 gap-1.5" aria-label={`Nivel de oportunidad: ${RANGE_LABELS[level]}`}>
        {SCORE_RANGES.map((r, i) => (
          <li key={r} className={cx("h-2 rounded-full", i <= idx ? "bg-accent" : "bg-line")} aria-hidden />
        ))}
      </ol>
      <p className="mt-3 text-sm text-ink-muted">{RANGE_DESCRIPTIONS[level]}</p>
    </div>
  );
}
