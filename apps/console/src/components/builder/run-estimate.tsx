"use client";

import * as React from "react";

import { ConfirmDialog } from "@nexus/ui";

import { moneyText } from "@/components/money/money-model";
import { useT } from "@/i18n/client";
import type { RunMoney, TestRunEstimate, TestRunScope } from "@/lib/backend/agent-quality-types";

import type { Result } from "./builder-model";

type Ids = { ref: string; agent: string };

export type EstimateRun = (body: Ids & { scope: TestRunScope }) => Promise<Result<TestRunEstimate>>;

/** Qué hay que decir antes de esa pasada. Las cuentas las hace la API, en una sola moneda. */
export type RunQuestion = "none" | "budget" | "charge" | "no_bag" | "no_price";

export function questionFor(data: TestRunEstimate): RunQuestion {
  if (data.payer === "client_bag") {
    if (!data.charge) return "no_price";
    return data.fits ? "charge" : "no_bag";
  }
  return data.fits ? "none" : "budget";
}

const read = (value: RunMoney | null) => (value ? moneyText(value) : "—");

type Asked = { scope: TestRunScope; tests: number; question: Exclude<RunQuestion, "none">; amount: string; left: string };

/**
 * Antes de una pasada (spec 047, 61.8, enmendado por el 66.5 y el 68). La que paga Auphere
 * no pregunta, salvo que no quepa en lo que queda de «Construcción y pruebas». La que paga
 * la bolsa del cliente siempre dice cuánto y cuánto hay, y solo arranca al confirmar; si no
 * llega, lleva al saldo del cliente. Si no se puede estimar, arranca igual y es ella la que
 * dice qué pasa.
 *
 * Lo preguntado se conserva al cerrar: el texto no cambia mientras se va el diálogo.
 */
export function useRunEstimate({
  estimate,
  ids,
  start,
  goTo = (href) => window.location.assign(href),
}: {
  estimate?: EstimateRun;
  ids: Ids;
  /** `confirmedTests`: cuántas pruebas vio y aceptó que cobrara la bolsa del cliente (68.4). */
  start: (scope: TestRunScope, confirmedTests?: number) => void | Promise<void>;
  goTo?: (href: string) => void;
}): { ask: (scope: TestRunScope) => Promise<void>; dialog: React.ReactNode; pending: boolean } {
  const t = useT();
  const [asked, setAsked] = React.useState<Asked | null>(null);
  const [open, setOpen] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  // Un doble clic no estima ni arranca dos veces.
  const asking = React.useRef(false);

  async function ask(scope: TestRunScope) {
    if (asking.current) return;
    asking.current = true;
    setPending(true);
    try {
      const res = estimate ? await estimate({ ...ids, scope }) : null;
      const question = res?.ok ? questionFor(res.data) : "none";
      if (!res?.ok || question === "none") {
        await start(scope);
        return;
      }
      setAsked({ scope, tests: res.data.tests, question, amount: read(res.data.charge), left: read(res.data.left) });
      setOpen(true);
    } finally {
      asking.current = false;
      setPending(false);
    }
  }

  const n = asked?.tests ?? 0;
  const money = { amount: asked?.amount ?? "", left: asked?.left ?? "" };
  const copy = {
    budget: {
      title: t(n === 1 ? "builder.suite.estimate.title.one" : "builder.suite.estimate.title.other", { n }),
      body: t("builder.suite.estimate.cost", money),
      confirm: t("builder.suite.estimate.confirm"),
    },
    charge: {
      title: t(n === 1 ? "builder.suite.charge.title.one" : "builder.suite.charge.title.other", { n }),
      body: t("builder.suite.charge.body", money),
      confirm: t("builder.suite.charge.confirm"),
    },
    no_bag: { title: t("builder.suite.noBag.title"), body: t("builder.suite.noBag.body", money), confirm: t("builder.suite.noBag.confirm") },
    no_price: { title: t("builder.suite.noPrice.title"), body: t("builder.suite.noPrice.body"), confirm: t("builder.suite.noPrice.confirm") },
  }[asked?.question ?? "budget"];

  const dialog = (
    <ConfirmDialog
      open={open}
      onOpenChange={setOpen}
      title={copy.title}
      description={copy.body}
      confirmLabel={copy.confirm}
      cancelLabel={t("common.cancel")}
      onConfirm={() => {
        setOpen(false);
        if (!asked || asked.question === "no_price") return;
        if (asked.question === "no_bag") goTo(`/clients/${encodeURIComponent(ids.ref)}?assign=1`);
        else if (asked.question === "charge") void start(asked.scope, asked.tests);
        else void start(asked.scope);
      }}
    />
  );

  return { ask, dialog, pending };
}
