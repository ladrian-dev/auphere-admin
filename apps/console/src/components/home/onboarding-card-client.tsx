"use client";

import { X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, Checklist, type ChecklistItem, Meter, Section, formatDuration } from "@nexus/ui";

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

  // The first pending step is where the partner is; the rest wait their turn.
  const firstPending = data?.steps.find((s) => !s.done)?.key;
  const items: ChecklistItem[] =
    data?.steps.map((s) => {
      const canFollow = s.key === "team" ? can(role, "team:read") : can(role, "clients:read");
      return {
        key: s.key,
        label: t(STEP_LABEL[s.key]),
        status: s.done ? "done" : s.key === firstPending ? "current" : "todo",
        href: !s.done && canFollow ? s.href : undefined,
      };
    }) ?? [];

  return (
    <Section
      id="onb"
      title={t("onb.title")}
      description={
        data ? (
          t("onb.progress", { done: data.done_count, total: data.total })
        ) : (
          <span role="alert" className="text-destructive">
            {t("onb.error")}
          </span>
        )
      }
      actions={
        <Button type="button" variant="ghost" size="icon-sm" onClick={dismiss} aria-label={t("onb.dismiss")}>
          <X className="size-4" aria-hidden="true" />
        </Button>
      }
    >
      {data ? (
        <>
          <Meter label={t("onb.title")} labelHidden value={data.done_count} max={data.total} tone="positive" size="sm" />
          <Checklist
            ariaLabel={t("onb.title")}
            items={items}
            renderLink={(item, children, className) => (
              <Link href={item.href ?? "#"} className={className}>
                {children}
              </Link>
            )}
          />
          <p className="font-mono text-xs text-muted-foreground text-pretty">
            {data.time_to_first_active_client_seconds != null
              ? t("onb.ttfa", { duration: formatDuration(data.time_to_first_active_client_seconds, locale) })
              : t("onb.ttfa.pending")}
          </p>
        </>
      ) : null}
    </Section>
  );
}
