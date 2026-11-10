"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, Field, NativeSelect, Textarea } from "@nexus/ui";
import { CURRENCIES, CURRENCY_IN_TEXT, CURRENCY_NAME, REASON_MAX, reasonError, type Currency } from "@/lib/levers";

import { setAccountCurrencyAction } from "./actions";
import { currencyConfirmText, currencyResultText, otherCurrency } from "./limits";

/**
 * Spec 047 (T172, 43.1): only Auphere changes the currency of a partner's
 * account. It converts what is left at the ECB's rate of the day and leaves an
 * entry, so the dialog says so before doing it. With the account's currency
 * known (`GET …/build-budget`) the only change is to the other one; without
 * it, the operator picks.
 */
export function AccountCurrencyForm({
  partnerId,
  partnerName,
  current,
}: {
  partnerId: string;
  partnerName: string;
  current: Currency | null;
}) {
  const router = useRouter();
  const [picked, setPicked] = useState<Currency>("EUR");
  const currency = current ? otherCurrency(current) : picked;
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function review() {
    setDone(null);
    const why = reasonError(reason);
    setError(why);
    if (why) return;
    setFailure(null);
    setOpen(true);
  }

  async function change() {
    setFailure(null);
    const result = await setAccountCurrencyAction(partnerId, { currency, reason: reason.trim() });
    if (!result.ok) {
      setFailure(result.error);
      return;
    }
    const line = currencyResultText(result.data);
    setDone(line);
    setOpen(false);
    setReason("");
    if (result.data.changed) toast.success(`La cuenta de ${partnerName} ya está en ${result.data.currency}`, { description: line });
    else toast.info(line);
    router.refresh();
  }

  return (
    <>
      <form
        className="flex flex-col gap-4"
        aria-label="Moneda de la cuenta"
        onSubmit={(e) => {
          e.preventDefault();
          review();
        }}
      >
        {current ? (
          <p className="text-sm">
            La cuenta está en {CURRENCY_IN_TEXT[current]}. Solo puede pasar a{" "}
            {CURRENCY_IN_TEXT[currency]}.
          </p>
        ) : (
          <Field label="Nueva moneda" hint="No se pudo leer la moneda de hoy: elige a cuál pasa.">
            {(a11y) => (
              <NativeSelect
                {...a11y}
                wrapperClassName="sm:w-48"
                value={picked}
                onChange={(e) => setPicked(e.target.value as Currency)}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {CURRENCY_NAME[c]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        )}
        <Field
          label="Motivo"
          required
          requiredLabel="Obligatorio"
          hint="Queda en la auditoría con tu nombre y el cambio aplicado."
          error={error ?? undefined}
        >
          {(a11y) => (
            <Textarea {...a11y} rows={2} maxLength={REASON_MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
          )}
        </Field>
        {done ? (
          <p role="status" className="text-sm text-pretty">
            {done}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button type="submit" variant="outline">
            {current ? `Cambiar a ${currency}…` : "Cambiar la moneda…"}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Cambiar la moneda de la cuenta de ${partnerName}`}
        description={currencyConfirmText(currency)}
        confirmLabel="Convertir y cambiar"
        cancelLabel="Cancelar"
        destructive
        onConfirm={change}
        error={failure}
      />
    </>
  );
}
