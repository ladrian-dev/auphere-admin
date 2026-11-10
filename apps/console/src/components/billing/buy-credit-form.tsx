"use client";

/**
 * Spec 005 · comprar crédito de consumo.
 *
 * **No acredita nada.** Abre la página del proveedor; el saldo sube cuando el
 * pago se confirma y llega el aviso. Esa separación es lo que permitió borrar
 * la puerta con la que un partner podía acreditarse solo.
 *
 * Dos decisiones de pantalla:
 *
 * **Los importes imposibles se paran aquí.** La API los rechazaría igual, pero
 * rebotar contra un 422 es peor forma de enterarse que un mensaje en el sitio
 * — y el error que esto previene, un cero de más, es el más caro que alguien
 * puede cometer en esta pantalla.
 *
 * **Se dice qué compra ese dinero antes de pagarlo.** «50 $» no significa
 * nada por sí solo: la relación entre dólares y lo que consume un turno es
 * justo lo que el partner no tiene por qué saber de memoria.
 */

import * as React from "react";
import { toast } from "sonner";

import { Button, Input, cn, formatCurrency, formatNumber } from "@nexus/ui";

import { buyCreditAction } from "@/app/(console)/billing/actions";
import { useLocale, useT } from "@/i18n/client";

/** Los mismos límites que valida la API, en unidades enteras de la moneda del cobro. */
const MIN_AMOUNT = 5;
const MAX_AMOUNT = 5_000;
/** Las cantidades rápidas del prototipo «Consola de partners v2». */
const QUICK = [20, 50, 100, 250] as const;
/**
 * La moneda en la que cobra el proveedor. Es la de `open_credit_session`
 * (`apps/api/.../billing/checkout.py`, `"currency": "usd"`): la consola no puede
 * prometer otra. Si la cuenta va en otra moneda, el formulario lo dice.
 */
export const CHECKOUT_CURRENCY = "USD";

/**
 * Spec 047 (45.3): «Recargar mi cuenta» llega con lo que faltaba para asignar
 * (`?recargar=`): el campo sale con ese importe, dentro de los límites.
 */
export function initialCreditAmount(raw: string | number | null | undefined): string {
  const n = Math.ceil(Number(raw));
  if (!Number.isFinite(n) || n <= 0) return "";
  return String(Math.min(MAX_AMOUNT, Math.max(MIN_AMOUNT, n)));
}

/**
 * Comprar saldo como en el prototipo: cuatro cantidades rápidas, «Otro importe»
 * y «Comprar», que se apaga fuera de 5 a 5000 en números enteros. Las cifras
 * salen de `Intl` con la moneda del cobro, nunca de un texto con «US$».
 */
export function BuyCreditForm({
  initialAmount,
  accountCurrency,
  label,
}: { initialAmount?: string | number | null; accountCurrency?: string | null; label?: string } = {}) {
  const t = useT();
  const locale = useLocale();
  const [quick, setQuick] = React.useState<number | null>(null);
  const [value, setValue] = React.useState(() => initialCreditAmount(initialAmount));
  const [pending, start] = React.useTransition();
  const id = React.useId();

  const typed = value.trim();
  const amount = quick ?? Number(typed);
  const valid = Number.isFinite(amount) && Number.isInteger(amount) && amount >= MIN_AMOUNT && amount <= MAX_AMOUNT && (quick !== null || typed !== "");
  const invalidTyped = quick === null && typed !== "" && !valid;
  const money = (n: number) => formatCurrency(n, CHECKOUT_CURRENCY, locale);
  const range = { min: formatNumber(MIN_AMOUNT, locale), max: formatNumber(MAX_AMOUNT, locale) };

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) {
      toast.error(t("proto.billing.credit.invalid", range));
      return;
    }
    start(async () => {
      const res = await buyCreditAction({ amount_cents: amount * 100 });
      if (!res.ok) {
        // Nunca el mensaje crudo del backend: la pantalla escribe la frase.
        // Y "no puedes" no es "no funciona": un rol sin permiso lo oye claro.
        toast.error(res.status === 403 ? t("common.forbidden") : t("membership.error.unavailable"));
        return;
      }
      if (res.data.url) window.location.assign(res.data.url);
    });
  }

  return (
    <form onSubmit={submit} className="grid min-w-0 gap-2" data-slot="buy-credit">
      {label ? <p className="text-sm font-medium" id={`${id}-label`}>{label}</p> : null}
      <div role="group" aria-label={t("proto.billing.quick")} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {QUICK.map((n) => (
          <button
            key={n}
            type="button"
            aria-pressed={quick === n}
            onClick={() => {
              setQuick(n);
              setValue("");
            }}
            className={cn(
              "h-12 rounded-lg border border-input bg-card text-md font-medium tabular-nums transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
              quick === n && "border-primary bg-status-positive-bg ring-1 ring-primary",
            )}
          >
            {money(n)}
          </button>
        ))}
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Input
          id={`${id}-amount`}
          name="amount"
          type="number"
          inputMode="numeric"
          min={MIN_AMOUNT}
          max={MAX_AMOUNT}
          step={1}
          value={value}
          placeholder={t("proto.billing.other")}
          aria-label={t("proto.billing.other")}
          onChange={(e) => {
            setQuick(null);
            setValue(e.target.value);
          }}
          className="min-w-0 flex-1"
          aria-invalid={invalidTyped || undefined}
          aria-describedby={`${id}-hint`}
        />
        <Button type="submit" disabled={pending || !valid}>
          {t("membership.credit.buy")}
        </Button>
      </div>
      <p id={`${id}-hint`} className={cn("text-sm text-pretty", invalidTyped ? "text-destructive" : "text-muted-foreground")} aria-live="polite">
        {invalidTyped
          ? t("proto.billing.credit.invalid", range)
          : valid
            ? `${t("membership.credit.buys", { amount: money(amount) })} ${t("proto.billing.secure")}`
            : t("proto.billing.credit.range", range)}
      </p>
      {accountCurrency && accountCurrency !== CHECKOUT_CURRENCY ? (
        <p className="text-xs text-pretty text-muted-foreground">{t("proto.billing.chargedIn", { currency: CHECKOUT_CURRENCY })}</p>
      ) : null}
    </form>
  );
}
