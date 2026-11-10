"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import {
  leversBackend,
  type AccountCurrencyChange,
  type BuildBudgetSaved,
  type Currency,
  type MoneyMicros,
} from "@/lib/backend-levers";
import { requireOperator } from "@/lib/session";

import { BUDGET_ERRORS, CURRENCY_ERRORS } from "./limits";

const path = (partnerId: string) => `/partners/${partnerId}/limits`;

/** Spec 047 (46.5, 54.5): the monthly «Construcción y pruebas» cap, with its reason. */
export async function setBuildBudgetAction(
  partnerId: string,
  body: { cap: MoneyMicros; reason: string },
): Promise<Result<BuildBudgetSaved>> {
  const operator = await requireOperator();
  try {
    const data = await leversBackend.setBuildBudget(partnerId, body, operator.id);
    revalidatePath(path(partnerId));
    return { ok: true, data: data as BuildBudgetSaved };
  } catch (err) {
    return toFailure(err, BUDGET_ERRORS);
  }
}

/** Spec 047 (43.1): only Auphere changes the account currency; it converts what is left. */
export async function setAccountCurrencyAction(
  partnerId: string,
  body: { currency: Currency; reason: string },
): Promise<Result<AccountCurrencyChange>> {
  const operator = await requireOperator();
  try {
    const data = await leversBackend.setAccountCurrency(partnerId, body, operator.id);
    revalidatePath(path(partnerId));
    revalidatePath(`/partners/${partnerId}`, "layout");
    return { ok: true, data: data as AccountCurrencyChange };
  } catch (err) {
    return toFailure(err, CURRENCY_ERRORS);
  }
}
