"use client";

import { Check, CircleDashed, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, cn, formatDuration } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Onboarding, OnboardingStepKey } from "@/lib/backend/onboarding";
import { can, type Role } from "@/lib/permissions";

export const ONBOARDING_DISMISS_KEY = "nexus.console.onboarding.dismissed";

const STEP_LABEL: Record<OnboardingStepKey, MessageKey> = {
  team: "onb.step.team",
  first_client: "onb.step.first_client",
  agent_published: "onb.step.agent_published",
  channel_connected: "onb.step.channel_connected",
  first_conversation: "onb.step.first_conversation",
};

// localStorage as an external store (per person, per browser — not partner data).
const listeners = new Set<() => void>();
function subscribeDismiss(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}
function readDismiss(): boolean | null {
  try {
    return window.localStorage.getItem(ONBOARDING_DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

// Five steps → five width stops (no inline styles: token discipline).
const PROGRESS_WIDTH = ["w-0", "w-1/5", "w-2/5", "w-3/5", "w-4/5", "w-full"] as const;

export function OnboardingCardClient({ data, role }: { data: Onboarding | null; role: Role }) {
  const t = useT();
  const locale = useLocale();
  const dismissed = React.useSyncExternalStore(subscribeDismiss, readDismiss, () => null);
  if (dismissed !== false) return null; // unknown (SSR) or dismissed → nothing (no layout jump on hydrate)
  if (data && data.complete) return null;

  function dismiss() {
    try {
      window.localStorage.setItem(ONBOARDING_DISMISS_KEY, "1");
    } catch {
      /* private mode */
    }
    for (const l of listeners) l();
  }

  return (
    <section aria-labelledby="onb-title" className="flex flex-col gap-3 rounded-md border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="onb-title" className="text-base font-semibold text-balance">
            {t("onb.title")}
          </h2>
          {data ? (
            <p className="text-sm text-muted-foreground">{t("onb.progress", { done: data.done_count, total: data.total })}</p>
          ) : (
            <p role="alert" className="text-sm text-destructive">
              {t("onb.error")}
            </p>
          )}
        </div>
        <Button type="button" variant="ghost" size="icon-sm" onClick={dismiss} aria-label={t("onb.dismiss")}>
          <X className="size-4" aria-hidden="true" />
        </Button>
      </div>
      {data ? (
        <>
          <div className="h-1 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={data.total} aria-valuenow={data.done_count} aria-label={t("onb.title")}>
            <div className={cn("h-full bg-primary transition-[width] duration-300", PROGRESS_WIDTH[Math.min(data.done_count, 5)])} />
          </div>
          <ol className="flex flex-col gap-1">
            {data.steps.map((s) => {
              const canFollow = s.key === "team" ? can(role, "team:read") : can(role, "clients:read");
              const inner = (
                <>
                  {s.done ? <Check className="size-4 shrink-0 text-primary" aria-hidden="true" /> : <CircleDashed className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
                  <span className={cn("min-w-0 truncate", s.done && "text-muted-foreground line-through")}>{t(STEP_LABEL[s.key])}</span>
                </>
              );
              return (
                <li key={s.key} className="text-sm">
                  {!s.done && canFollow ? (
                    <Link href={s.href} className="flex min-w-0 items-center gap-2 rounded-sm px-1 py-1 hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
                      {inner}
                    </Link>
                  ) : (
                    <span className="flex min-w-0 items-center gap-2 px-1 py-1">{inner}</span>
                  )}
                </li>
              );
            })}
          </ol>
          <p className="font-mono text-xs text-muted-foreground text-pretty">
            {data.time_to_first_active_client_seconds != null
              ? t("onb.ttfa", { duration: formatDuration(data.time_to_first_active_client_seconds, locale) })
              : t("onb.ttfa.pending")}
          </p>
        </>
      ) : null}
    </section>
  );
}
