"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button, Field, Input, StatusBadge, Textarea } from "@nexus/ui";
import type { BuildBudget } from "@/lib/backend-levers";
import { CURRENCY_IN_TEXT, REASON_MAX, formatMicros, microsToInput } from "@/lib/levers";

import { setBuildBudgetAction } from "./actions";
import { BUDGET_STATE, budgetSummary, checkBudget, monthLabel } from "./limits";

/**
 * Spec 047 (T172; 46.5, 54.5): the partner's monthly cap of «Construcción y
 * pruebas», in money and in the currency of its account (the API says which;
 * the operator does not choose it). The form starts from this month's cap.
 * Saving changes this month's (raising it unblocks at once) and the months to
 * come; the reason goes to the audit.
 */
export function BuildBudgetForm({ partnerId, budget }: { partnerId: string; budget: BuildBudget }) {
  const router = useRouter();
  const currency = budget.currency;
  const [amount, setAmount] = useState(() => microsToInput(budget.cap.amount_micros));
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<{ amount?: string; reason?: string }>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const state = BUDGET_STATE[budget.state];

  async function submit() {
    setFailure(null);
    setSaved(null);
    const check = checkBudget({ amount, currency, reason });
    if (!check.ok) {
      setErrors(check.errors);
      return;
    }
    setErrors({});
    setPending(true);
    try {
      const result = await setBuildBudgetAction(partnerId, { cap: check.cap, reason: check.reason });
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      const line = `Tope de ${monthLabel(result.data.month)} y de los meses que vienen: ${formatMicros(
        result.data.cap.amount_micros,
        result.data.cap.currency,
      )}.`;
      setSaved(line);
      toast.success("Tope guardado", { description: line });
      setReason("");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        {state ? <StatusBadge tone={state.tone}>{state.label}</StatusBadge> : null}
        <span>{budgetSummary(budget)}</span>
      </p>
      <form
        className="flex flex-col gap-4"
        aria-label="Tope de Construcción y pruebas"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field
          label={`Tope mensual (${currency})`}
          required
          requiredLabel="Obligatorio"
          hint={`En ${CURRENCY_IN_TEXT[currency]}, la moneda de la cuenta del partner, con dos decimales como mucho. 0 detiene la construcción y las pruebas.`}
          error={errors.amount}
        >
          {(a11y) => (
            <Input
              {...a11y}
              inputMode="decimal"
              autoComplete="off"
              className="sm:w-48"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          )}
        </Field>
        <Field
          label="Motivo"
          required
          requiredLabel="Obligatorio"
          hint="Queda en la auditoría con tu nombre. Por ejemplo: «Amplía para el lanzamiento de noviembre»."
          error={errors.reason}
        >
          {(a11y) => (
            <Textarea {...a11y} rows={2} maxLength={REASON_MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
          )}
        </Field>
        {failure ? (
          <p role="alert" className="text-sm text-destructive text-pretty">
            {failure}
          </p>
        ) : null}
        {saved ? (
          <p role="status" className="text-sm text-pretty">
            {saved}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button type="submit" disabled={pending}>
            {pending ? "Guardando…" : "Guardar el tope"}
          </Button>
        </div>
      </form>
    </div>
  );
}
