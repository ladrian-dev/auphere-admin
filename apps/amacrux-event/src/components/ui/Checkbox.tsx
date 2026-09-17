"use client";

import { forwardRef, useId, type InputHTMLAttributes } from "react";

import { cx } from "@/lib/cx";

export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  description?: string;
  error?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox({ label, description, error, id, className, ...rest }, ref) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const errorId = `${inputId}-error`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className={cx("flex cursor-pointer items-start gap-3 rounded-md border-2 p-3.5", error ? "border-danger" : "border-line", className)}>
        <input
          ref={ref}
          id={inputId}
          type="checkbox"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className="mt-0.5 size-5 shrink-0 accent-(--accent-deep)"
          {...rest}
        />
        <span className="flex flex-col">
          <span className="text-sm font-medium text-ink">{label}</span>
          {description ? <span className="text-xs text-ink-muted">{description}</span> : null}
        </span>
      </label>
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
});
