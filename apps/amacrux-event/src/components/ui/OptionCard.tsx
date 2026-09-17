"use client";

import { cx } from "@/lib/cx";

import { CheckIcon } from "./icons";

export interface OptionCardProps {
  label: string;
  description?: string;
  selected: boolean;
  disabled?: boolean;
  mode: "single" | "multi";
  onToggle: () => void;
  compact?: boolean;
  /** Píldora densa para listas largas de selección múltiple. */
  pill?: boolean;
}

export function OptionCard({ label, description, selected, disabled = false, mode, onToggle, compact = false, pill = false }: OptionCardProps) {
  if (pill) {
    return (
      <button
        type="button"
        role={mode === "single" ? "radio" : "checkbox"}
        aria-checked={selected}
        aria-disabled={disabled || undefined}
        onClick={() => {
          if (!disabled) onToggle();
        }}
        className={cx(
          "flex min-h-10 w-full items-center gap-2 rounded-full border-2 px-3 py-1.5 text-left text-[13px] font-medium leading-tight transition-[border-color,background-color] duration-(--duration-fast)",
          selected ? "border-accent-deep bg-accent/25 text-ink" : "border-line bg-surface text-ink hover:border-ink-muted",
          disabled && !selected && "cursor-not-allowed opacity-45",
        )}
      >
        <span aria-hidden className={cx("flex size-4 shrink-0 items-center justify-center rounded-full border-2", selected ? "border-accent-deep bg-accent text-accent-contrast" : "border-line bg-canvas text-transparent")}>
          <CheckIcon size={11} />
        </span>
        <span className="min-w-0">{label}</span>
      </button>
    );
  }
  return (
    <button
      type="button"
      role={mode === "single" ? "radio" : "checkbox"}
      aria-checked={selected}
      aria-disabled={disabled || undefined}
      onClick={() => {
        if (!disabled) onToggle();
      }}
      className={cx(
        "group flex w-full items-start gap-3 rounded-md border-2 bg-surface text-left transition-[border-color,background-color,box-shadow,transform] duration-(--duration-fast) ease-(--ease-out)",
        compact ? "min-h-12 px-3 py-2.5" : "min-h-14 px-4 py-3.5",
        selected ? "border-accent-deep bg-surface shadow-glow" : "border-line hover:border-ink-muted",
        disabled && !selected && "cursor-not-allowed opacity-45",
        "active:scale-[0.995]",
      )}
    >
      <span
        aria-hidden
        className={cx(
          "mt-px flex size-5 shrink-0 items-center justify-center border-2 transition-colors duration-(--duration-fast)",
          mode === "single" ? "rounded-full" : "rounded-sm",
          selected ? "border-accent-deep bg-accent text-accent-contrast" : "border-line bg-canvas text-transparent",
        )}
      >
        <CheckIcon size={12} />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="text-[14px] font-medium leading-tight text-ink [overflow-wrap:anywhere]">{label}</span>
        {description ? <span className="mt-0.5 text-sm leading-snug text-ink-muted">{description}</span> : null}
      </span>
    </button>
  );
}
