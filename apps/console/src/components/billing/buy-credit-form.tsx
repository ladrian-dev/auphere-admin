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

import { Button, Input, Label } from "@nexus/ui";

import { buyCreditAction } from "@/app/(console)/billing/actions";
import { useLocale, useT } from "@/i18n/client";
import { formatMoney } from "@/lib/money";

/** Los mismos límites que valida la API, en dólares. */
const MIN_USD = 5;
const MAX_USD = 5_000;

export function BuyCreditForm() {
  const t = useT();
  const locale = useLocale();
  const [value, setValue] = React.useState("");
  const [pending, start] = React.useTransition();

  const amount = Number(value);
  const valid = Number.isFinite(amount) && Number.isInteger(amount) && amount >= MIN_USD && amount <= MAX_USD;
  // Spec 027: lo que se paga es lo que se recibe, en dinero. La consola no
  // conoce la tasa interna ni habla de unidades.
  const receives = valid ? amount * 100 : null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) {
      toast.error(t("membership.credit.invalid", { min: MIN_USD, max: MAX_USD }));
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
    <form onSubmit={submit} className="flex flex-col gap-2">
      <Label htmlFor="credit-amount">{t("membership.credit.amount")}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          id="credit-amount"
          name="amount"
          type="number"
          inputMode="numeric"
          min={MIN_USD}
          max={MAX_USD}
          step={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-32"
          aria-describedby="credit-hint"
        />
        <Button type="submit" size="sm" disabled={pending}>
          {t("membership.credit.buy")}
        </Button>
      </div>
      <p id="credit-hint" className="text-muted-foreground text-sm" aria-live="polite">
        {receives === null
          ? t("membership.credit.range", { min: MIN_USD, max: MAX_USD })
          : t("membership.credit.buys", { amount: formatMoney(receives, locale) })}
      </p>
    </form>
  );
}
