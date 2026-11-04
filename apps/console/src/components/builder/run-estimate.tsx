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

/** ¿Hay algo que preguntar? Solo si la pasada no cabe en lo que queda de la partida. */
export function doesNotFit(data: TestRunEstimate): boolean {
  if (!data.estimate || !data.budget) return false;
  return data.estimate.amount_micros > data.budget.remaining_micros;
}

/**
 * Antes de una pasada (spec 047, 61.8, enmendado por el 66.5). «Construcción y pruebas» la
 * paga Auphere hasta el tope, así que una pasada normal no pregunta nada: lo medido sale
 * en Uso. Solo se pregunta si no cabe en lo que queda, porque entonces no terminará. Si no
 * se puede estimar, arranca igual y es ella la que dice qué pasa (sin partida, sin versión).
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
  const [asked, setAsked] = React.useState<{ scope: TestRunScope; tests: number; cents: number; left: number } | null>(null);

  async function ask(scope: TestRunScope) {
    const res = estimate ? await estimate({ ...ids, scope }) : null;
    if (!res?.ok || !doesNotFit(res.data)) {
      await start(scope);
      return;
    }
    setAsked({
      scope,
      tests: res.data.tests,
      cents: estimateCents(res.data.estimate) ?? 0,
      left: Math.floor((res.data.budget?.remaining_micros ?? 0) / 10_000),
    });
  }

  const dialog = (
    <ConfirmDialog
      open={asked !== null}
      onOpenChange={(open) => {
        if (!open) setAsked(null);
      }}
      title={t(asked?.tests === 1 ? "builder.suite.estimate.title.one" : "builder.suite.estimate.title.other", { n: asked?.tests ?? 0 })}
      description={t("builder.suite.estimate.cost", {
        amount: formatMoney(asked?.cents ?? 0, locale),
        left: formatMoney(asked?.left ?? 0, locale),
      })}
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
