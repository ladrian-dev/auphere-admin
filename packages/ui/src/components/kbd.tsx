"use client";

import * as React from "react";

import { cn } from "../lib/utils";

/** Keyboard key hint (⌘K, Esc, ↵). Mono, quiet, never the only affordance. */
function Kbd({ className, ...props }: React.ComponentProps<"kbd">) {
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


/** "⌘K" on a Mac, "Ctrl K" everywhere else. Pure so it can be tested. */
function shortcutLabel(keyName: string, isMac: boolean): string {
  return isMac ? `⌘${keyName}` : `Ctrl ${keyName}`;
}

function detectMac(): boolean {
  if (typeof navigator === "undefined") return true;
  const ua = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform ?? navigator.platform ?? "";
  return /mac|iphone|ipad/i.test(ua);
}

/**
 * A modifier-plus-key hint that names the modifier the reader actually
 * has. Renders the Mac form first (the server cannot know), then corrects
 * itself after mount without a hydration warning.
 */
function ShortcutKbd({ keyName, className, ...props }: React.ComponentProps<"kbd"> & { keyName: string }) {
  const [isMac, setIsMac] = React.useState(true);
  React.useEffect(() => setIsMac(detectMac()), []);
  return (
    <Kbd className={className} suppressHydrationWarning {...props}>
      {shortcutLabel(keyName, isMac)}
    </Kbd>
  );
}

export { Kbd, ShortcutKbd, shortcutLabel };
