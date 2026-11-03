"use client";

import * as React from "react";

import { ConfirmDialog } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { TestRunEstimate, TestRunScope } from "@/lib/backend/agent-quality-types";
import { formatMoney } from "@/lib/money";

import type { Result } from "./builder-model";

type Ids = { ref: string; agent: string };

export type EstimateRun = (body: Ids & { scope: TestRunScope }) => Promise<Result<TestRunEstimate>>;

/** Micro-dollars to cents: a pass that costs something never reads as nothing. */
export function estimateCents(estimate: TestRunEstimate["estimate"]): number | null {
  if (!estimate) return null;
  return Math.max(1, Math.round(estimate.amount_micros / 10_000));
}

/**
 * Antes de una pasada, cuánto costará (spec 047, 61.8). Es una estimación: lo
 * medido sale en «Construcción y pruebas». Si no se puede estimar, la pasada
 * arranca igual y es ella la que dice qué pasa (sin partida, sin versión).
 */
export function useRunEstimate({
  estimate,
  ids,
  start,
}: {
  estimate?: EstimateRun;
  ids: Ids;
  start: (scope: TestRunScope) => void | Promise<void>;
}): { ask: (scope: TestRunScope) => Promise<void>; dialog: React.ReactNode } {
  const t = useT();
  const locale = useLocale();
  const [asked, setAsked] = React.useState<{ scope: TestRunScope; tests: number; cents: number | null } | null>(null);

  async function ask(scope: TestRunScope) {
    if (!estimate) {
      await start(scope);
      return;
    }
    const res = await estimate({ ...ids, scope });
    if (!res.ok) {
      await start(scope);
      return;
    }
    setAsked({ scope, tests: res.data.tests, cents: estimateCents(res.data.estimate) });
  }

  const dialog = (
    <ConfirmDialog
      open={asked !== null}
      onOpenChange={(open) => {
        if (!open) setAsked(null);
      }}
      title={t(asked?.tests === 1 ? "builder.suite.estimate.title.one" : "builder.suite.estimate.title.other", { n: asked?.tests ?? 0 })}
      description={
        asked?.cents != null
          ? t("builder.suite.estimate.cost", { amount: formatMoney(asked.cents, locale) })
          : t("builder.suite.estimate.unknown")
      }
      confirmLabel={t("builder.suite.estimate.confirm")}
      cancelLabel={t("common.cancel")}
      onConfirm={() => {
        const scope = asked?.scope;
        setAsked(null);
        if (scope) void start(scope);
      }}
    />
  );

  return { ask, dialog };
}
