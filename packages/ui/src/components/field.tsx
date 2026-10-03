import * as React from "react";

import { cn } from "../lib/utils";
import { Label } from "./label";

type FieldA11y = {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
  "aria-required": true | undefined;
};

type FieldProps = {
  label: React.ReactNode;
  /** The control's id; generated when omitted. */
  htmlFor?: string;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  required?: boolean;
  /** «Opcional» / «Obligatorio» — the caller's words. */
  optionalLabel?: React.ReactNode;
  requiredLabel?: React.ReactNode;
  /** The control, given the ids it must carry. */
  children: (a11y: FieldA11y) => React.ReactNode;
  className?: string;
};

/**
 * Label + control + hint + error, wired (Bloque C). The console had four
 * sizes of error text and two ways of writing ``aria-describedby``; here the
 * control gets its ids from one place, the hint stays readable when there is
 * an error, and the error is announced.
 */
function Field({ label, htmlFor, hint, error, required, optionalLabel, requiredLabel, children, className }: FieldProps) {
  const generated = React.useId();
  const id = htmlFor ?? `field-${generated}`;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div data-slot="field" className={cn("flex min-w-0 flex-col gap-(--space-inline)", className)}>
      <Label htmlFor={id} className="min-w-0">
        <span className="min-w-0 truncate">{label}</span>
        {required && requiredLabel ? <span className="text-xs font-normal text-muted-foreground">{requiredLabel}</span> : null}
        {!required && optionalLabel ? <span className="text-xs font-normal text-muted-foreground">{optionalLabel}</span> : null}
      </Label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined, "aria-required": required ? true : undefined })}
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-destructive text-pretty">
          {error}
        </p>
      ) : null}
      {hint ? (
        <p id={hintId} className="text-xs text-muted-foreground text-pretty">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export { Field, type FieldA11y, type FieldProps };
