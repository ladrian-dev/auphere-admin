import { ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "../lib/utils";

type NativeSelectProps = Omit<React.ComponentProps<"select">, "size"> & {
  /** Control height, like ``Input``. The native ``size`` (rows) is not exposed. */
  size?: "sm" | "md";
  wrapperClassName?: string;
};

/**
 * The browser's own ``<select>``, dressed like an Input (Bloque C). Twelve
 * files carried a copy of these classes; the keyboard, the mobile picker
 * and the form semantics stay native — the Base UI ``Select`` is for when a
 * design needs more than a list.
 */
function NativeSelect({ className, wrapperClassName, size = "md", children, ...props }: NativeSelectProps) {
  return (
    <span className={cn("relative inline-flex min-w-0 max-w-full", wrapperClassName)} data-slot="native-select">
      <select
        className={cn(
          "w-full min-w-0 cursor-pointer appearance-none rounded-md border border-input bg-transparent pr-8 pl-3 text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:bg-input/30",
          size === "sm" ? "h-7" : "h-8",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
    </span>
  );
}

export { NativeSelect, type NativeSelectProps };
