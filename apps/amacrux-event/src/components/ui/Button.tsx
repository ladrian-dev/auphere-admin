"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cx } from "@/lib/cx";

type Variant = "primary" | "accent" | "secondary" | "ghost";
type Size = "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  loadingLabel?: string;
  full?: boolean;
}

const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-contrast hover:opacity-95 active:opacity-90 shadow-2",
  accent: "bg-accent text-accent-contrast hover:bg-accent-deep active:bg-accent-deep shadow-2",
  secondary: "bg-surface text-ink border border-line hover:border-ink-muted active:bg-canvas",
  ghost: "bg-transparent text-ink hover:bg-surface active:bg-canvas",
};

const sizes: Record<Size, string> = {
  md: "h-12 px-5 text-base",
  lg: "h-14 px-6 text-lg",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, loadingLabel = "Un momento…", full = false, className, children, disabled, type = "button", ...rest },
  ref,
) {
  const isDisabled = disabled || loading;
  return (
    <button
      ref={ref}
      type={type}
      aria-busy={loading || undefined}
      disabled={isDisabled}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md font-display font-semibold transition-[opacity,background-color,border-color,transform] duration-(--duration-fast) ease-(--ease-out)",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none",
        "active:scale-[0.99]",
        variants[variant],
        sizes[size],
        full && "w-full",
        className,
      )}
      {...rest}
    >
      {loading ? (
        <>
          <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />
          <span>{loadingLabel}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
});
