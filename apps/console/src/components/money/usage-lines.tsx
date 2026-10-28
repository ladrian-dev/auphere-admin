"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Meter } from "@nexus/ui";

import { requestBuildExtensionAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { BuildBudget, UsageLineOut } from "@/lib/backend/money-types";

import { LINE_LABEL, buildShare, moneyErrorText, moneyText, type Failed } from "./money-model";

type Result<T> = { ok: true; data: T } | Failed;
export type BuildActions = { requestMore: () => Promise<Result<{ status: string }>> };
const SERVER: BuildActions = { requestMore: () => requestBuildExtensionAction() };

/**
 * Las cuatro partidas de Consumo (spec 047, requisito 46.4), cada una con quién
 * la paga: «Conversaciones» (la bolsa de cada cliente), «Mensajes de Meta» (el
 * negocio, a Meta, como estimación), «Construcción y pruebas» (Auphere, hasta el
 * tope mensual del partner, con su barra y «Pedir ampliación») y «Companion y
 * teammates» (la cuenta). La construcción nunca se cuenta en tokens (46.5).
 */
export function UsageLines({ lines, build, actions = SERVER }: { lines: UsageLineOut[]; build: BuildBudget | null; actions?: BuildActions }) {
  const t = useT();
  return (
    <ul className="grid min-w-0 gap-3 md:grid-cols-2" data-slot="usage-lines">
      {lines.map((l) => (
        <li key={l.line} id={l.line === "build" ? "construccion" : undefined} className="grid min-w-0 scroll-mt-24 gap-2 rounded-md border border-border bg-card p-4" data-line={l.line}>
          <div className="flex min-w-0 items-baseline justify-between gap-3">
            <h3 className="min-w-0 text-sm font-semibold text-pretty">{t(LINE_LABEL[l.line])}</h3>
            <span className="shrink-0 text-base font-semibold whitespace-nowrap tabular-nums">
              {l.approx ? `${t("money.approxPrefix")} ` : ""}
              {moneyText(l.amount)}
            </span>
          </div>
          <p className="text-xs text-pretty text-muted-foreground">{t(`money.line.${l.line}.payer` as MessageKey)}</p>
          {l.line === "build" ? <BuildLine line={l} build={build} actions={actions} /> : null}
        </li>
      ))}
    </ul>
  );
}

function BuildLine({ line, build, actions }: { line: UsageLineOut; build: BuildBudget | null; actions: BuildActions }) {
  const t = useT();
  const [busy, setBusy] = React.useState(false);
  const [sent, setSent] = React.useState<"sent" | "today" | null>(null);
  const cap = build?.cap ?? line.cap ?? null;
  const spent = build?.spent ?? line.amount;
  const state = build?.state ?? line.state ?? "ok";
  const share = buildShare(spent, cap);

  async function ask() {
    setBusy(true);
    const res = await actions.requestMore();
    setBusy(false);
    if (res.ok) {
      setSent("sent");
      toast.success(t("money.build.requested"));
      return;
    }
    if (res.code === "request_already_sent_today" || res.status === 429) {
      setSent("today");
      return;
    }
    toast.error(moneyErrorText(t, res));
  }

  return (
    <div className="grid min-w-0 gap-2" data-slot="build-line">
      {cap ? (
        <Meter
          value={spent.amount_micros}
          max={cap.amount_micros}
          size="sm"
          label={t("money.build.cap.label")}
          labelHidden
          valueLabel={t("money.build.cap.value", { spent: moneyText(spent), cap: moneyText(cap), pct: Math.round((share ?? 0) * 100) })}
        />
      ) : null}
      {state === "exhausted" ? (
        <p className="text-sm text-pretty text-destructive" role="status">
          {t("money.build.exhausted")}
        </p>
      ) : state === "warning" ? (
        <p className="text-sm text-pretty text-status-warning-text" role="status">
          {t("money.build.warning")}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {sent ? (
          <p className="text-sm text-muted-foreground" role="status">
            {sent === "sent" ? t("money.build.requested") : t("money.build.already")}
          </p>
        ) : (
          <Button type="button" size="sm" variant={state === "ok" ? "outline" : "default"} loading={busy} onClick={() => void ask()}>
            {t("money.build.ask")}
          </Button>
        )}
      </div>
    </div>
  );
}
