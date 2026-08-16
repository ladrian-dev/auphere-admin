import type { ComponentProps } from "react";

import { cn } from "../lib/utils";

/** Mono, uppercase, tracked label above a title. Editorial marker. */
function Eyebrow({ className, ...props }: ComponentProps<"p">) {
  return (
    <p
      data-slot="eyebrow"
      className={cn("font-mono text-xs tracking-eyebrow text-muted-foreground uppercase", className)}
      {...props}
    />
  );
}

export { Eyebrow };
