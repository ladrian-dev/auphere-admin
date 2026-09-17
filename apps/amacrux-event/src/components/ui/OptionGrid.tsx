"use client";

import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

export interface OptionGridProps {
  legend: string;
  hint?: string;
  mode: "single" | "multi";
  columns?: 1 | 2;
  status?: string;
  children: ReactNode;
}

export function OptionGrid({ legend, hint, mode, columns = 1, status, children }: OptionGridProps) {
  return (
    <fieldset className="min-w-0 border-0 p-0">
      <legend className="mb-1 font-display text-2xl font-bold leading-tight text-ink sm:text-3xl">{legend}</legend>
      {hint ? <p className="mb-2 text-sm text-ink-muted">{hint}</p> : <span className="block h-2" />}
      <div role={mode === "single" ? "radiogroup" : "group"} aria-label={legend} className={cx("grid gap-2", columns === 2 && "grid-cols-2")}>
        {children}
      </div>
      {status ? (
        <p className="mt-2 text-sm text-ink-muted" aria-live="polite">
          {status}
        </p>
      ) : null}
    </fieldset>
  );
}
