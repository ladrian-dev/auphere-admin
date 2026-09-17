import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

type Tone = "neutral" | "accent" | "success" | "warning" | "navy";

const tones: Record<Tone, string> = {
  neutral: "bg-canvas text-ink-muted border-line",
  accent: "bg-accent/20 text-ink border-accent/60",
  success: "bg-success/12 text-success border-success/40",
  warning: "bg-warning/12 text-warning border-warning/40",
  navy: "bg-primary text-primary-contrast border-primary",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide", tones[tone], className)}>
      {children}
    </span>
  );
}
