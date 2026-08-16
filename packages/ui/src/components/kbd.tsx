import type { ComponentProps } from "react";

import { cn } from "../lib/utils";

/** Keyboard key hint (⌘K, Esc, ↵). Mono, quiet, never the only affordance. */
function Kbd({ className, ...props }: ComponentProps<"kbd">) {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-border bg-muted px-1 font-mono text-xs text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export { Kbd };
