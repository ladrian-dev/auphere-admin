"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@nexus/ui";

import { lowerBalanceAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";
import type { BagOut, Money } from "@/lib/backend/money-types";

import { moneyErrorText, moneyText, newIdempotencyKey, type Failed } from "./money-model";

type Result<T> = { ok: true; data: T } | Failed;
export type ReturnActions = { lower: (body: { ref: string; amount: Money; key: string }) => Promise<Result<BagOut>> };
const SERVER: ReturnActions = { lower: (b) => lowerBalanceAction(b) };

/**
 * Al archivar un cliente con saldo en su bolsa (spec 047, requisito 43.13): «A
 * {cliente} le quedan X. ¿Lo devuelves a tu cuenta?». Devolver es bajar la bolsa
 * por lo que queda; dejarlo no cambia nada (no caduca, 43.6).
 */
export function ReturnBagDialog({
  refId,
  name,
  amount,
  onOpenChange,
  actions = SERVER,
}: {
  refId: string;
  name: string;
  amount: Money;
  onOpenChange: (open: boolean) => void;
  actions?: ReturnActions;
}) {
  const t = useT();
  const router = useRouter();
  const [error, setError] = React.useState<string | null>(null);
  const key = React.useMemo(() => newIdempotencyKey("archive-return"), []);

  async function back() {
    setError(null);
    const res = await actions.lower({ ref: refId, amount, key });
    if (!res.ok) {
      setError(moneyErrorText(t, res, amount.currency));
      return;
    }
    toast.success(t("money.return.done", { amount: moneyText(amount, "down"), name }));
    onOpenChange(false);
    router.refresh();
  }

  return (
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      title={t("money.return.title")}
      description={t("money.return.body", { name, amount: moneyText(amount, "down") })}
      confirmLabel={t("money.return.confirm")}
      cancelLabel={t("money.return.keep")}
      onConfirm={back}
      error={error}
    />
  );
}
