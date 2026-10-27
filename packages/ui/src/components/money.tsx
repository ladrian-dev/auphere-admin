import type { ComponentProps } from "react";

import { EM_DASH } from "../lib/format";
import { cn } from "../lib/utils";

/**
 * Dinero — spec 047 (R45.9).
 *
 * Todo importe se lee igual en toda la consola: `es-ES`, dos decimales,
 * separador de miles **siempre** (es-ES no lo pone con cuatro cifras: sin
 * `useGrouping: "always"` saldría «1234,50 €») y el símbolo detrás: «€» para
 * el euro y el código para el dólar («60,00 USD», no «60,00 US$»). Solo hay
 * euros y dólares (research, la bolsa en la moneda del cliente).
 *
 * El formato es fijo en `es-ES` a propósito: el requisito lo pide así para
 * todo partner, y un mismo saldo no puede leerse distinto en la lista de
 * clientes, en Consumo y en un aviso (R46.7).
 */
export type Currency = "EUR" | "USD";

/** El dinero tal como lo manda la API (`contracts/console-api.md`, «Dinero»). */
export type MoneyValue = { amount_micros: number; currency: Currency };

/**
 * `amount_micros` va en cien milésimas de la moneda (`data-model.md`:
 * «Importes en `bigint` de cien milésimas de su moneda»). Un solo sitio para
 * la escala: si el contrato cambia, cambia aquí.
 */
export const MICROS_PER_UNIT = 100_000;

const SYMBOL: Record<Currency, string> = { EUR: "€", USD: "USD" };

const NUMBER = new Intl.NumberFormat("es-ES", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  // `true` is «always» (Intl.NumberFormat v3): es-ES would otherwise leave
  // four-digit amounts ungrouped («1234,50»). Not the string form: the
  // desktop app and companion-ui compile against a lib that types it boolean.
  useGrouping: true,
});

/** «1.234,50 €» · «60,00 USD» · «—» si no hay importe. El espacio es duro: no se parte. */
export function formatMoney(amount: number | null | undefined, currency: Currency): string {
  if (amount == null || !Number.isFinite(amount)) return EM_DASH;
  return `${NUMBER.format(amount)} ${SYMBOL[currency]}`;
}

/** De la API a unidades de la moneda. */
export function moneyFromMicros(value: MoneyValue): { amount: number; currency: Currency } {
  return { amount: value.amount_micros / MICROS_PER_UNIT, currency: value.currency };
}

type MoneyProps = Omit<ComponentProps<"span">, "children"> &
  ({ amount: number | null | undefined; currency: Currency; value?: never } | { value: MoneyValue; amount?: never; currency?: never });

/** Un importe en línea: números tabulares (las cifras se alinean en columna) y sin partirse. */
function Money({ amount, currency, value, className, ...props }: MoneyProps) {
  const money = value ? moneyFromMicros(value) : { amount, currency: currency as Currency };
  return (
    <span data-slot="money" className={cn("whitespace-nowrap tabular-nums", className)} {...props}>
      {formatMoney(money.amount, money.currency)}
    </span>
  );
}

export { Money, type MoneyProps };
