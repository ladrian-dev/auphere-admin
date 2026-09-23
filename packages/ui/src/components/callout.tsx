"use client";

import { AlertTriangle, CheckCircle2, Info, OctagonAlert, X } from "lucide-react";
import * as React from "react";

import { cn } from "../lib/utils";
import { Button } from "./button";

type CalloutTone = "neutral" | "info" | "positive" | "warning" | "danger";

type CalloutProps = {
  tone?: CalloutTone;
  title?: React.ReactNode;
  children?: React.ReactNode;
  /** A button or link that resolves the callout. */
  action?: React.ReactNode;
  /** The ×. ``persistKey`` remembers the dismissal in localStorage. */
  dismissible?: boolean;
  dismissLabel?: string;
  onDismiss?: () => void;
  persistKey?: string;
  icon?: boolean;
  className?: string;
};

const TONE: Record<CalloutTone, string> = {
  neutral: "border-border bg-card text-card-foreground",
  info: "border-status-info-border bg-status-info-bg text-foreground",
  positive: "border-status-positive-border bg-status-positive-bg text-foreground",
  warning: "border-status-warning-border bg-status-warning-bg text-foreground",
  danger: "border-status-danger-border bg-status-danger-bg text-foreground",
};

const ICON: Record<CalloutTone, React.ElementType | null> = {
  neutral: null,
  info: Info,
  positive: CheckCircle2,
  warning: AlertTriangle,
  danger: OctagonAlert,
};

const ICON_TONE: Record<CalloutTone, string> = {
  neutral: "",
  info: "text-status-info-text",
  positive: "text-status-positive-text",
  warning: "text-warning",
  danger: "text-destructive",
};

function readDismissed(key: string | undefined): boolean {
  if (!key || typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(`callout:${key}`) === "1";
  } catch {
    return false;
  }
}

/**
 * A banner that means something (Bloque C): five tones with a fixed meaning
 * — positive = done, warning = near a limit or needs action, danger = error
 * or irreversible, info = pending — and never decoration. Warning and danger
 * are ``role="alert"``; the rest are ``role="status"``.
 */
function Callout({ tone = "neutral", title, children, action, dismissible, dismissLabel, onDismiss, persistKey, icon = true, className }: CalloutProps) {
  const [dismissed, setDismissed] = React.useState(() => readDismissed(persistKey));
  if (dismissed) return null;
  const Glyph = icon ? ICON[tone] : null;
  function dismiss() {
    setDismissed(true);
    onDismiss?.();
    if (persistKey) {
      try {
        window.localStorage.setItem(`callout:${persistKey}`, "1");
      } catch {
        /* sin almacenamiento: se vuelve a mostrar la próxima vez */
      }
    }
  }
  return (
    <div
      data-slot="callout"
      data-tone={tone}
      role={tone === "warning" || tone === "danger" ? "alert" : "status"}
      className={cn("flex min-w-0 items-start gap-(--space-stack) rounded-md border px-3 py-2 text-sm", TONE[tone], className)}
    >
      {Glyph ? <Glyph className={cn("mt-1 size-4 shrink-0", ICON_TONE[tone])} aria-hidden="true" /> : null}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {title ? <p className="font-medium text-balance">{title}</p> : null}
        {children ? <div className="text-pretty text-muted-foreground [&_a]:underline [&_a]:underline-offset-4">{children}</div> : null}
        {action ? <div className="pt-1">{action}</div> : null}
      </div>
      {dismissible ? (
        <Button type="button" variant="ghost" size="icon-xs" onClick={dismiss} aria-label={dismissLabel} className="-mt-1 -mr-1 shrink-0">
          <X aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}

export { Callout, type CalloutProps, type CalloutTone };
