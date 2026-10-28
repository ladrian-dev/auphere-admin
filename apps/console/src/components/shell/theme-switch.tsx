"use client";

import { Moon, Sun } from "lucide-react";
import * as React from "react";

import { cn, useTheme } from "@nexus/ui";

import { useT } from "@/i18n/client";

/**
 * Claro u oscuro, como un interruptor junto a la campana (Andrés, 2026-10-28),
 * de la misma altura que el buscador (32 px).
 * Sin elegir, sigue al sistema; al pulsarlo se queda con el que se ve. En el
 * servidor el tema no se sabe: hasta montar pinta el claro, igual en los dos
 * lados, y así la hidratación no choca.
 */
const noop = () => () => {};
export function ThemeSwitch({ className }: { className?: string }) {
  const t = useT();
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = React.useSyncExternalStore(noop, () => true, () => false);
  const dark = mounted && resolvedTheme === "dark";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label={t("shell.theme.switch")}
      onClick={() => setTheme(dark ? "light" : "dark")}
      className={cn(
        "relative inline-flex h-8 w-14 shrink-0 items-center rounded-full bg-muted p-1 ring-1 ring-foreground/10 outline-none transition-colors duration-(--duration-hover) focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "grid size-6 place-items-center rounded-full bg-(--tab-on) text-foreground shadow-sm transition-transform duration-(--duration-state) ease-(--ease-out) motion-reduce:transition-none",
          dark ? "translate-x-6" : "translate-x-0",
        )}
      >
        {dark ? <Moon className="size-4" strokeWidth={1.75} /> : <Sun className="size-4" strokeWidth={1.75} />}
      </span>
    </button>
  );
}
