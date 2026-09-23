"use client";

import { CircleHelp } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";

type HelpHintProps = {
  /** The explanation. Also the accessible name of the trigger. */
  children: ReactNode;
  /** Screen-reader name when ``children`` is not plain text. */
  label?: string;
  className?: string;
};

/**
 * A small «?» with the explanation on hover, focus or tap (Bloque C).
 * Replaces the ``title=`` attributes nobody could reach from a keyboard or
 * a phone: the trigger is a real button, so it has focus and a name.
 */
function HelpHint({ children, label, className }: HelpHintProps) {
  const name = label ?? (typeof children === "string" ? children : undefined);
  return (
    <TooltipProvider delay={300}>
      <Tooltip>
        <TooltipTrigger
          data-slot="help-hint"
          aria-label={name}
          className={cn(
            "inline-flex size-6 shrink-0 cursor-help items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
            className,
          )}
        >
          <CircleHelp className="size-4" aria-hidden="true" />
        </TooltipTrigger>
        <TooltipContent className="max-w-64 text-pretty">
          {children}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export { HelpHint, type HelpHintProps };
