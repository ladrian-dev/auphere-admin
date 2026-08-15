"use client";

import { ThemeProvider as NextThemesProvider, useTheme } from "next-themes";
import type { ComponentProps } from "react";

/**
 * Drives ``[data-theme="dark"]`` (what tokens.css keys on). Wrap the app
 * root once. ``attribute="data-theme"`` is the whole reason this exists —
 * without it the dark palette is unreachable.
 */
function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="data-theme"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}

export { ThemeProvider, useTheme };
