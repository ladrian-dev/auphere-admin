"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Field, Input, NativeSelect, Skeleton } from "@nexus/ui";

import { bagChoicesAction, eurUsdAction, moveBalanceAction, setBagCurrencyAction, setRefillAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";
import type { BagChoice, BagOut, Currency, Fx, Money } from "@/lib/backend/money-types";

import { amountInputValue, convertMicros, eurUsdOf, fxLine, money, moneyErrorText, moneyText, newIdempotencyKey, parseAmount, type Failed } from "./money-model";

type Result<T> = { ok: true; data: T } | Failed;

export type BagActions = {
  choices: () => Promise<Result<BagChoice[]>>;
  fx: () => Promise<Result<Fx>>;
  move: (body: { from_ref: string; to_ref: string; amount: Money; key: string }) => Promise<Result<BagOut[]>>;
  refill: (body: { ref: string; up_to: Money | null }) => Promise<Result<BagOut>>;
  currency: (body: { ref: string; currency: Currency; confirm: boolean }) => Promise<Result<BagOut>>;
};
const SERVER: BagActions = {
  choices: () => bagChoicesAction(),
  fx: () => eurUsdAction(),
  move: (b) => moveBalanceAction(b),
  refill: (b) => setRefillAction(b),
  currency: (b) => setBagCurrencyAction(b),
};

/** Lo que estas ventanas saben de la bolsa de origen. */
export type BagRef = { ref: string; name: string; balance: Money | null; refillUpTo: Money | null };

const symbol = (c: Currency) => (c === "EUR" ? "€" : "USD");

/**
 * «Mover saldo a otro cliente» (spec 047, requisito 43.7): un solo traspaso, o
 * cambian las dos bolsas o no cambia ninguna. Si las monedas son distintas, se
 * enseña la conversión al cambio del día antes de confirmar.
 */
export function MoveDialog({ from, onOpenChange, actions = SERVER }: { from: BagRef; onOpenChange: (open: boolean) => void; actions?: BagActions }) {
  const t = useT();
  const router = useRouter();
  const [choices, setChoices] = React.useState<BagChoice[] | null>(null);
  const [fx, setFx] = React.useState<Fx | null>(null);
  const [to, setTo] = React.useState("");
  const [value, setValue] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const keyRef = React.useRef<{ sig: string; key: string } | null>(null);
  const source = from.balance;

  React.useEffect(() => {
    let live = true;
    void actions.choices().then((res) => {
      if (!live) return;
      if (res.ok) setChoices(res.data.filter((c) => c.ref !== from.ref));
      else setError(moneyErrorText(t, res));
    });
    return () => {
      live = false;
    };
  }, [actions, from.ref, t]);

  const target = choices?.find((c) => c.ref === to) ?? null;
  const cross = Boolean(source && target && target.currency !== source.currency);
  React.useEffect(() => {
    if (!cross || fx) return;
    let live = true;
    void actions.fx().then((res) => {
      if (live && res.ok) setFx(res.data);
    });
    return () => {
      live = false;
    };
  }, [actions, cross, fx]);

  if (!source) return null;
  const parsed = parseAmount(value);
  const micros = parsed.kind === "ok" ? parsed.micros : 0;
  const tooMuch = micros > source.amount_micros;
  const fieldError =
    parsed.kind === "invalid"
      ? t("money.amount.invalid")
      : parsed.kind === "ok" && micros <= 0
        ? t("money.amount.positive")
        : tooMuch
          ? t("money.move.tooMuch", { amount: moneyText(source, "down") })
          : null;
  const eurUsd = fx ? eurUsdOf(fx.rate, "EUR", "USD") : null;
  const receives = target && micros > 0 && !tooMuch ? (cross ? (eurUsd != null ? money(convertMicros(micros, source.currency, target.currency, eurUsd), target.currency) : null) : money(micros, target.currency)) : null;
  const canSubmit = Boolean(target) && micros > 0 && !fieldError && (!cross || eurUsd != null) && !busy;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || !target || !source) return;
    const sig = `${target.ref}:${micros}`;
    if (!keyRef.current || keyRef.current.sig !== sig) keyRef.current = { sig, key: newIdempotencyKey("move") };
    setBusy(true);
    setError(null);
    const res = await actions.move({ from_ref: from.ref, to_ref: target.ref, amount: money(micros, source.currency), key: keyRef.current.key });
    setBusy(false);
    if (res.ok) {
      toast.success(t("money.move.done", { amount: moneyText(money(micros, source.currency)), from: from.name, to: target.name }));
      onOpenChange(false);
      router.refresh();
      return;
    }
    setError(moneyErrorText(t, res, source.currency));
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="move-dialog">
          <DialogHeader>
            <DialogTitle>{t("money.move.title", { name: from.name })}</DialogTitle>
            <DialogDescription>{t("money.move.body", { amount: moneyText(source, "down") })}</DialogDescription>
          </DialogHeader>
          {!choices && !error ? (
            <Skeleton className="h-16 w-full" />
          ) : choices && choices.length === 0 ? (
            <p className="text-sm text-pretty text-muted-foreground">{t("money.move.nobody")}</p>
          ) : choices ? (
            <>
              <Field label={t("money.move.to")}>
                {(a11y) => (
                  <NativeSelect {...a11y} value={to} onChange={(e) => setTo(e.target.value)}>
                    <option value="">{t("money.move.pick")}</option>
                    {choices.map((c) => (
                      <option key={c.ref} value={c.ref}>
                        {c.name} · {c.currency}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Field label={t("money.move.amount", { currency: symbol(source.currency) })} hint={t("money.amount.hint")} error={fieldError ?? undefined}>
                {(a11y) => <Input {...a11y} inputMode="decimal" autoComplete="off" value={value} placeholder="0,00" className="max-w-40 tabular-nums" onChange={(e) => setValue(e.target.value)} />}
              </Field>
              <p role="status" aria-live="polite" className="text-sm text-pretty" data-slot="move-preview">
                {target && receives
                  ? t("money.move.receives", { name: target.name, amount: moneyText(receives) }) + (cross && eurUsd != null ? ` (${fxLine(t, eurUsd, fx?.date ?? null)})` : "")
                  : target && cross && eurUsd == null && micros > 0
                    ? t("money.error.fx_unavailable")
                    : ""}
              </p>
            </>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-pretty text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("money.cancel")}
            </Button>
            <Button type="submit" loading={busy} disabled={!canSubmit}>
              {t("money.move.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** «Rellenar cada mes hasta…» (43.8): el día 1 (UTC) la bolsa sube hasta ese importe con dinero de la cuenta. */
export function RefillDialog({ bag, currency, onOpenChange, actions = SERVER }: { bag: BagRef; currency: Currency; onOpenChange: (open: boolean) => void; actions?: BagActions }) {
  const t = useT();
  const router = useRouter();
  const [on, setOn] = React.useState(bag.refillUpTo != null);
  const [value, setValue] = React.useState(bag.refillUpTo ? amountInputValue(bag.refillUpTo.amount_micros) : "");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const parsed = parseAmount(value);
  const fieldError = on && parsed.kind !== "ok" ? t("money.amount.invalid") : on && parsed.kind === "ok" && parsed.micros <= 0 ? t("money.amount.positive") : null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (fieldError) return;
    setBusy(true);
    setError(null);
    const upTo = on && parsed.kind === "ok" ? money(parsed.micros, currency) : null;
    const res = await actions.refill({ ref: bag.ref, up_to: upTo });
    setBusy(false);
    if (res.ok) {
      toast.success(upTo ? t("money.refill.saved", { name: bag.name, amount: moneyText(upTo) }) : t("money.refill.removed", { name: bag.name }));
      onOpenChange(false);
      router.refresh();
      return;
    }
    setError(moneyErrorText(t, res, currency));
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="refill-dialog">
          <DialogHeader>
            <DialogTitle>{t("money.refill.title", { name: bag.name })}</DialogTitle>
            <DialogDescription>{t("money.refill.body")}</DialogDescription>
          </DialogHeader>
          <label className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 size-4 shrink-0 accent-primary" checked={on} onChange={(e) => setOn(e.target.checked)} />
            <span className="text-pretty">{t("money.refill.check")}</span>
          </label>
          {on ? (
            <Field label={t("money.refill.amount", { currency: symbol(currency) })} hint={t("money.refill.hint")} error={fieldError ?? undefined}>
              {(a11y) => <Input {...a11y} inputMode="decimal" autoComplete="off" value={value} placeholder="0,00" className="max-w-40 tabular-nums" onChange={(e) => setValue(e.target.value)} />}
            </Field>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-pretty text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("money.cancel")}
            </Button>
            <Button type="submit" loading={busy} disabled={Boolean(fieldError)}>
              {t("money.refill.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * La moneda de la bolsa (43.3): con saldo dentro, la API dice cuánto quedaría al
 * cambio del día y se confirma; sin saldo, se cambia sin más.
 */
export function CurrencyDialog({ bag, current, onOpenChange, actions = SERVER }: { bag: BagRef; current: Currency; onOpenChange: (open: boolean) => void; actions?: BagActions }) {
  const t = useT();
  const router = useRouter();
  const base = React.useId();
  const [next, setNext] = React.useState<Currency>(current === "EUR" ? "USD" : "EUR");
  const [confirming, setConfirming] = React.useState<{ wouldBe: Money; line: string | null } | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (next === current) return onOpenChange(false);
    setBusy(true);
    setError(null);
    const res = await actions.currency({ ref: bag.ref, currency: next, confirm: confirming != null });
    setBusy(false);
    if (res.ok) {
      toast.success(t("money.currency.done", { name: bag.name, amount: moneyText(res.data.balance, "down") }));
      onOpenChange(false);
      router.refresh();
      return;
    }
    if (res.code === "confirm_required") {
      const would = res.info?.would_be as Money | undefined;
      const fx = res.info?.fx as Fx | undefined;
      const eurUsd = fx ? eurUsdOf(fx.rate, current, next) : null;
      if (would) {
        setConfirming({ wouldBe: would, line: eurUsd != null ? fxLine(t, eurUsd, fx?.date ?? null) : null });
        return;
      }
    }
    setError(moneyErrorText(t, res, current));
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="currency-dialog">
          <DialogHeader>
            <DialogTitle>{t("money.currency.title", { name: bag.name })}</DialogTitle>
            <DialogDescription>{t("money.currency.body", { current })}</DialogDescription>
          </DialogHeader>
          <fieldset className="grid min-w-0 gap-2" disabled={confirming != null}>
            <legend className="mb-1 text-sm font-medium">{t("money.currency.legend")}</legend>
            {(["EUR", "USD"] as const).map((c) => (
              <label key={c} className="flex min-h-6 items-center gap-2 text-sm">
                <input type="radio" name={`${base}-currency`} className="size-4 accent-primary" checked={next === c} onChange={() => setNext(c)} />
                {t(c === "EUR" ? "money.currency.eur" : "money.currency.usd")}
              </label>
            ))}
          </fieldset>
          {confirming ? (
            <p role="status" className="rounded-md bg-muted/50 p-3 text-sm text-pretty" data-slot="currency-confirm">
              {t("money.currency.confirm", { from: moneyText(bag.balance, "down"), to: moneyText(confirming.wouldBe, "down") })}
              {confirming.line ? <span className="block text-xs text-muted-foreground">{confirming.line}</span> : null}
            </p>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-pretty text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("money.cancel")}
            </Button>
            <Button type="submit" loading={busy} disabled={next === current}>
              {confirming ? t("money.currency.confirmSubmit", { currency: next }) : t("money.currency.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
