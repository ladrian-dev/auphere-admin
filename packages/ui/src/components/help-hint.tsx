"use client";

import { CircleHelp } from "lucide-react";
import { type ReactNode, useState } from "react";

import { cn } from "../lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";

type HelpHintProps = {
  /** The explanation, shown in the tooltip. */
  children: ReactNode;
  /** The accessible name of the «?» («Ayuda: Crédito»). Falls back to the
   *  text of the explanation. */
  label?: string;
  side?: "top" | "bottom";
  className?: string;
};

/** The hint that is currently open, so opening one closes it. */
let openHint: ((v: boolean) => void) | null = null;

/**
 * A small «?» with the explanation on hover, focus or tap (Bloque C).
 * Replaces the ``title=`` attributes nobody could reach from a keyboard or
 * a phone: the trigger is a real button, so it has focus and a name.
 */
function HelpHint({ children, label, side = "bottom", className }: HelpHintProps) {
  const name = label ?? (typeof children === "string" ? children : undefined);
  // Es un botón: quien lo pulsa espera que pase algo. Sin esto solo se abría
  // al pasar el ratón o al llegar con el tabulador, y en una pantalla táctil
  // no se abría nunca.
  const [open, setOpen] = useState(false);
  // Solo uno abierto a la vez: apilados se tapan entre sí y el de arriba
  // cubre el título de la página.
  function change(next: boolean) {
    if (next) {
      if (openHint && openHint !== setOpen) openHint(false);
      openHint = setOpen;
    } else if (openHint === setOpen) {
      openHint = null;
    }
    setOpen(next);
  }
  return (
    <TooltipProvider delay={300}>
      <Tooltip open={open} onOpenChange={change}>
        <TooltipTrigger
          data-slot="help-hint"
          aria-label={name}
          aria-expanded={open}
          onClick={() => change(!open)}
          className={cn(
            "inline-flex size-6 shrink-0 cursor-help items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
            className,
          )}
        >
          <CircleHelp className="size-4" aria-hidden="true" />
        </TooltipTrigger>
        <TooltipContent side={side} role="tooltip" className="max-w-64 text-pretty">
          {children}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export { HelpHint, type HelpHintProps };
