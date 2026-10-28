"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Input, StatusBadge } from "@nexus/ui";

import { confirmMigrationAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";
import type { Currency, MigrationAdjust, MigrationConfirmed, MigrationProposal } from "@/lib/backend/money-types";

import { amountInputValue, migrationAdjust, money, moneyErrorText, moneyText, type Failed } from "./money-model";

type Result<T> = { ok: true; data: T } | Failed;
export type MigrationActions = { confirm: (body: { adjust?: MigrationAdjust }) => Promise<Result<MigrationConfirmed>> };
const SERVER: MigrationActions = { confirm: (b) => confirmMigrationAction(b) };

/**
 * «Repartir tu saldo en bolsas» (spec 047, T160, requisito 55.3): con la consola
 * nueva, cada cliente tiene su bolsa. La propuesta es lo que le queda este mes a
 * cada uno con su tope de hoy, y se puede ajustar antes de confirmar (en la
 * moneda de la cuenta: cada bolsa lo recibe convertido a la suya). Al confirmar,
 * eso pasa a su bolsa y el partner deja los topes. Hasta entonces sus clientes
 * siguen respondiendo con el tope de hoy. Confirmar es de owners y admins.
 */
export function MigrationWizard({
  proposal,
  names,
  canConfirm,
  currency,
  actions = SERVER,
}: {
  proposal: MigrationProposal;
  names: Record<string, string>;
  canConfirm: boolean;
  /** La moneda de la cuenta, en la que se ajusta. Sin ella, la de la propuesta. */
  currency?: Currency | null;
  actions?: MigrationActions;
}) {
  const t = useT();
  const router = useRouter();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState<number | null>(proposal.confirmed_at ? -1 : null);
  const [values, setValues] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(proposal.clients.map((c) => [c.ref, amountInputValue(c.amount.amount_micros)])),
  );
  const cur: Currency = currency ?? proposal.clients[0]?.amount.currency ?? "USD";
  const sym = cur === "EUR" ? "€" : "USD";
  const plan = migrationAdjust(proposal, values);

  async function confirm() {
    if (plan.invalid.length) return;
    setBusy(true);
    setError(null);
    const res = await actions.confirm(Object.keys(plan.adjust).length ? { adjust: plan.adjust } : {});
    setBusy(false);
    if (res.ok) {
      setDone(res.data.clients);
      toast.success(t("money.migration.done", { n: res.data.clients }));
      router.refresh();
      return;
    }
    if (res.code === "already_confirmed") {
      setDone(-1);
      return;
    }
    setError(res.code === "invalid_adjust" ? t("money.migration.invalidAdjust") : moneyErrorText(t, res));
  }

  if (done != null) {
    return (
      <Callout
        tone="positive"
        title={t("money.migration.confirmed.title")}
        action={
          <Button size="sm" nativeButton={false} render={<Link href="/usage" />}>
            {t("money.migration.toUsage")}
          </Button>
        }
      >
        {done >= 0 ? t("money.migration.done", { n: done }) : t("money.migration.confirmed.body")}
      </Callout>
    );
  }

  if (proposal.clients.length === 0) {
    return (
      <Callout
        tone="info"
        title={t("money.migration.nothing.title")}
        action={
          <Button size="sm" nativeButton={false} render={<Link href="/usage" />}>
            {t("money.migration.toUsage")}
          </Button>
        }
      >
        {t("money.migration.nothing.body")}
      </Callout>
    );
  }

  return (
    <div className="grid min-w-0 gap-6" data-slot="migration-wizard">
      <ol className="grid min-w-0 gap-2 text-sm text-pretty">
        {(["money.migration.step1", "money.migration.step2", "money.migration.step3"] as const).map((key, i) => (
          <li key={key} className="flex gap-2">
            <StatusBadge tone="info" dot={false}>
              {i + 1}
            </StatusBadge>
            <span>{t(key)}</span>
          </li>
        ))}
      </ol>

      <div className="relative min-w-0 overflow-x-auto rounded-md border border-border" role="region" aria-label={t("money.migration.table")} tabIndex={0}>
        <table className="w-full min-w-[480px] border-collapse text-left text-sm">
          <caption className="sr-only">{t("money.migration.table")}</caption>
          <thead className="bg-muted/50 text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">{t("money.table.client")}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t("money.migration.proposed")}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t("money.migration.amount")}</th>
            </tr>
          </thead>
          <tbody>
            {proposal.clients.map((c) => {
              const name = names[c.ref] ?? c.ref;
              const wrong = plan.invalid.includes(c.ref);
              return (
                <tr key={c.ref} className="border-t border-border" data-client={c.ref}>
                  <td className="max-w-64 truncate px-3 py-2" title={name}>
                    {name}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap text-muted-foreground tabular-nums">{moneyText(c.amount, "down")}</td>
                  <td className="px-3 py-2 text-right">
                    {canConfirm ? (
                      <Input
                        aria-label={t("money.migration.adjust", { name, currency: sym })}
                        aria-invalid={wrong || undefined}
                        inputMode="decimal"
                        autoComplete="off"
                        value={values[c.ref] ?? ""}
                        onChange={(e) => setValues((v) => ({ ...v, [c.ref]: e.target.value }))}
                        className="ml-auto max-w-32 text-right tabular-nums"
                      />
                    ) : (
                      <span className="whitespace-nowrap tabular-nums">{moneyText(c.amount, "down")}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-border font-semibold">
              <th scope="row" className="px-3 py-2 text-left" colSpan={2}>
                {t("money.migration.total")}
              </th>
              <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums" data-slot="migration-total">
                {moneyText(money(plan.total, cur), "down")}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {plan.invalid.length ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {t("money.amount.invalid")}
        </p>
      ) : null}
      <p className="text-sm text-pretty text-muted-foreground">{t("money.migration.until")}</p>
      {error ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {error}
        </p>
      ) : null}
      {canConfirm ? (
        <div className="flex flex-wrap gap-2">
          <Button type="button" loading={busy} disabled={plan.invalid.length > 0} onClick={() => void confirm()}>
            {t("money.migration.confirm")}
          </Button>
          <Button variant="outline" nativeButton={false} render={<Link href="/usage" />}>
            {t("money.migration.later")}
          </Button>
        </div>
      ) : (
        <p className="text-sm text-pretty">{t("money.migration.ownersOnly")}</p>
      )}
    </div>
  );
}
