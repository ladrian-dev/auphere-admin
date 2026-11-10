"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Input,
  Skeleton,
  cn,
  formatMoney,
} from "@nexus/ui";

import { assignBalanceAction, bagContextAction, lowerBalanceAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";
import type { BagContext, BagOut, Money, Receipt } from "@/lib/backend/money-types";

import {
  QUICK_AMOUNTS,
  amountInputValue,
  assignPreview,
  assignedText,
  convertMicros,
  eurUsdOf,
  fxLine,
  missingOf,
  money,
  moneyErrorText,
  moneyText,
  newIdempotencyKey,
  parseAmount,
  rechargeHref,
  units,
  type Failed,
  type T,
} from "./money-model";

type Result<T> = { ok: true; data: T } | Failed;

export type AssignActions = {
  context: (body: { ref: string }) => Promise<Result<BagContext>>;
  assign: (body: { ref: string; amount: Money; refill_up_to?: Money | null; alert_low?: boolean; key: string }) => Promise<Result<Receipt>>;
  lower: (body: { ref: string; amount: Money; key: string }) => Promise<Result<BagOut>>;
};
const SERVER: AssignActions = {
  context: (b) => bagContextAction(b),
  assign: (b) => assignBalanceAction(b),
  lower: (b) => lowerBalanceAction(b),
};

/** Dónde se confirma el reparto en bolsas (55.3, T160). */
export const MIGRATION_HREF = "/usage/repartir";

type Direction = "up" | "down";

/**
 * «Asignar saldo a {cliente}» (spec 047, requisito 45): se abre en el sitio,
 * sin cambiar de pantalla, desde la lista de clientes, el Panel del cliente,
 * «Necesita tu atención», la tabla de Consumo, la página del canal y el aviso
 * de «Pedir saldo».
 *
 * - Las cantidades rápidas (10, 20, 50 y 100 en la moneda de la bolsa) y
 *   «Otra cantidad», que admite coma decimal.
 * - El recibo, anunciado (`role=status`): el saldo actual, lo que se asigna, lo
 *   que sale de la cuenta (con la línea del BCE si las monedas son distintas),
 *   el nuevo saldo y lo que queda en la cuenta. Si no llega, «Faltan» en rojo,
 *   «Recargar mi cuenta» para quien compra y el botón desactivado. Si la
 *   cuenta se queda con menos del 20 %, un aviso ámbar que no bloquea.
 * - «Rellenar cada mes hasta…» y «Avisarme cuando le quede menos del 20 %»,
 *   marcada por defecto.
 *
 * Con `change`, es «Cambiar saldo» (45.6): subir o bajar la bolsa. Bajar
 * devuelve a la cuenta, como mucho, lo que queda (43.6).
 */
export function AssignDialog({
  refId,
  name,
  change = false,
  initialDirection = "up",
  onOpenChange,
  actions = SERVER,
}: {
  refId: string;
  name: string;
  /** «Cambiar saldo»: deja elegir entre subir y bajar. */
  change?: boolean;
  initialDirection?: Direction;
  onOpenChange: (open: boolean) => void;
  actions?: AssignActions;
}) {
  const t = useT();
  const [ctx, setCtx] = React.useState<BagContext | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [direction, setDirection] = React.useState<Direction>(initialDirection);
  const base = React.useId();

  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    let live = true;
    void actions.context({ ref: refId }).then((res) => {
      if (!live) return;
      if (res.ok) setCtx(res.data);
      else setLoadError(moneyErrorText(t, res));
    });
    return () => {
      live = false;
    };
  }, [actions, refId, t, attempt]);

  function retry() {
    setLoadError(null);
    setAttempt((n) => n + 1);
  }

  const title = change ? t("money.change.title", { name }) : t("money.assign.title", { name });

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-slot="assign-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{change ? t("money.change.body") : t("money.assign.body")}</DialogDescription>
        </DialogHeader>
        {loadError ? (
          <div className="grid gap-3">
            <p role="alert" className="text-sm text-pretty text-destructive">
              {loadError}
            </p>
            <Button variant="outline" size="sm" className="w-fit" onClick={retry}>
              {t("money.retry")}
            </Button>
          </div>
        ) : !ctx ? (
          <div className="grid gap-3" aria-busy="true">
            <span role="status" className="sr-only">
              {t("money.loading")}
            </span>
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <>
            {change ? (
              <fieldset className="grid min-w-0 gap-2">
                <legend className="sr-only">{t("money.change.direction")}</legend>
                <div className="inline-flex w-fit max-w-full flex-wrap rounded-md bg-muted p-1">
                  {(["up", "down"] as const).map((d) => (
                    <label
                      key={d}
                      className={cn(
                        "cursor-pointer rounded-sm px-3 py-1 text-sm font-medium has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                        direction === d ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      <input type="radio" name={`${base}-direction`} className="sr-only" checked={direction === d} onChange={() => setDirection(d)} />
                      {t(d === "up" ? "money.change.up" : "money.change.down")}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}
            {direction === "up" ? (
              <AssignForm refId={refId} name={name} ctx={ctx} actions={actions} onClose={() => onOpenChange(false)} />
            ) : (
              <LowerForm refId={refId} name={name} ctx={ctx} actions={actions} onClose={() => onOpenChange(false)} />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── subir: «Asignar saldo» ─────────────────────────────────────────────────

type Choice = { kind: "quick"; value: number } | { kind: "other" };

function AssignForm({ refId, name, ctx, actions, onClose }: { refId: string; name: string; ctx: BagContext; actions: AssignActions; onClose: () => void }) {
  const t = useT();
  const router = useRouter();
  const base = React.useId();
  const bagCurrency = ctx.bag.balance.currency;
  const [choice, setChoice] = React.useState<Choice>({ kind: "quick", value: QUICK_AMOUNTS[1] });
  const [other, setOther] = React.useState("");
  const [refillOn, setRefillOn] = React.useState(ctx.bag.refill_up_to != null);
  const [refill, setRefill] = React.useState(ctx.bag.refill_up_to ? amountInputValue(ctx.bag.refill_up_to.amount_micros) : "");
  const [alertLow, setAlertLow] = React.useState(ctx.bag.alert_low);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<{ text: string; code: string | null } | null>(null);
  const [serverMissing, setServerMissing] = React.useState<Money | null>(null);
  const keyRef = React.useRef<{ micros: number; key: string } | null>(null);

  const parsed = choice.kind === "quick" ? ({ kind: "ok", micros: units(choice.value) } as const) : parseAmount(other);
  const micros = parsed.kind === "ok" ? parsed.micros : 0;
  const amountError =
    choice.kind === "other" && parsed.kind === "invalid"
      ? t("money.amount.invalid")
      : choice.kind === "other" && parsed.kind === "ok" && micros <= 0
        ? t("money.amount.positive")
        : null;
  const eurUsd = ctx.eurUsd ? eurUsdOf(ctx.eurUsd.rate, "EUR", "USD") : null;
  const preview = micros > 0 ? assignPreview({ amountMicros: micros, bag: ctx.bag.balance, available: ctx.available, eurUsd }) : null;
  const noFx = bagCurrency !== ctx.available.currency && eurUsd == null;
  const missing = preview?.missing ?? serverMissing;
  const refillParsed = parseAmount(refill);
  const refillError = refillOn && refillParsed.kind !== "ok" ? t("money.amount.invalid") : refillOn && refillParsed.kind === "ok" && refillParsed.micros <= 0 ? t("money.amount.positive") : null;
  const canSubmit = ctx.bagsActive && !noFx && micros > 0 && !amountError && !missing && !refillError && !busy;

  function pick(next: Choice) {
    setChoice(next);
    setServerMissing(null);
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    if (!keyRef.current || keyRef.current.micros !== micros) keyRef.current = { micros, key: newIdempotencyKey("assign") };
    setBusy(true);
    setError(null);
    const upTo = refillOn && refillParsed.kind === "ok" ? money(refillParsed.micros, bagCurrency) : ctx.bag.refill_up_to ? null : undefined;
    const res = await actions.assign({
      ref: refId,
      amount: money(micros, bagCurrency),
      ...(upTo !== undefined ? { refill_up_to: upTo } : {}),
      alert_low: alertLow,
      key: keyRef.current.key,
    });
    setBusy(false);
    if (res.ok) {
      const text = assignedText(t, res.data, name);
      if (res.data.warn_low_account) toast.warning(text, { description: t("money.receipt.lowAccount") });
      else toast.success(text);
      onClose();
      router.refresh();
      return;
    }
    const gap = missingOf(res);
    if (gap) {
      setServerMissing(gap);
      return;
    }
    setError({ text: moneyErrorText(t, res, bagCurrency), code: res.code ?? null });
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="assign-form">
      {!ctx.bagsActive ? <MigrationFirst t={t} /> : null}
      <fieldset className="grid min-w-0 gap-2">
        <legend className="mb-1 text-sm font-medium">{t("money.amount.legend")}</legend>
        <div className="flex min-w-0 flex-wrap gap-2">
          {QUICK_AMOUNTS.map((q) => (
            <Pill key={q} name={`${base}-amount`} checked={choice.kind === "quick" && choice.value === q} onChange={() => pick({ kind: "quick", value: q })}>
              {formatMoney(q, bagCurrency)}
            </Pill>
          ))}
          <Pill name={`${base}-amount`} checked={choice.kind === "other"} onChange={() => pick({ kind: "other" })}>
            {t("money.amount.other")}
          </Pill>
        </div>
      </fieldset>
      {choice.kind === "other" ? (
        <Field label={t("money.amount.otherLabel", { currency: bagCurrency === "EUR" ? "€" : "USD" })} hint={t("money.amount.hint")} error={amountError ?? undefined}>
          {(a11y) => (
            <Input
              {...a11y}
              inputMode="decimal"
              autoComplete="off"
              autoFocus
              value={other}
              placeholder="0,00"
              className="max-w-40 tabular-nums"
              onChange={(e) => {
                setOther(e.target.value);
                setServerMissing(null);
                setError(null);
              }}
            />
          )}
        </Field>
      ) : null}

      <div role="status" aria-live="polite" aria-atomic="true" data-slot="assign-receipt" className="grid min-w-0 gap-2 rounded-md bg-muted/50 p-3 text-sm">
        <p className="font-medium">{t("money.receipt.title")}</p>
        <dl className="grid min-w-0 gap-1">
          <Row label={t("money.receipt.before", { name })} value={moneyText(ctx.bag.balance, "down")} />
          <Row label={t("money.receipt.assigned")} value={preview ? moneyText(preview.assigned) : "—"} />
          <Row
            label={t("money.receipt.debit")}
            note={preview?.eurUsd != null ? fxLine(t, preview.eurUsd, ctx.eurUsd?.date ?? null) : null}
            value={preview ? moneyText(preview.debit) : "—"}
          />
          <Row label={t("money.receipt.after")} value={preview ? moneyText(preview.after, "down") : "—"} strong />
          <Row label={t("money.receipt.left")} value={preview && !missing ? moneyText(preview.left, "down") : moneyText(missing ? money(0, ctx.available.currency) : ctx.available, "down")} />
        </dl>
        {noFx ? <p className="text-pretty text-destructive">{t("money.error.fx_unavailable")}</p> : null}
        {missing ? (
          <div className="grid gap-1" data-slot="assign-missing">
            <p className="font-medium text-destructive">{t("money.receipt.missing", { amount: moneyText(missing) })}</p>
            {ctx.canRecharge ? (
              <Link href={rechargeHref(missing)} className="w-fit font-medium text-primary-text underline-offset-4 hover:underline">
                {t("money.receipt.recharge")}
              </Link>
            ) : (
              <p className="text-xs text-pretty text-muted-foreground">{t("money.receipt.askBilling")}</p>
            )}
          </div>
        ) : preview?.lowAccount ? (
          <p className="rounded-sm border border-status-warning-border bg-status-warning-bg px-2 py-1 text-pretty" data-slot="assign-low">
            {t("money.receipt.lowAccount")}
          </p>
        ) : null}
      </div>

      <div className="grid min-w-0 gap-2">
        <label className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1 size-4 shrink-0 accent-primary" checked={refillOn} onChange={(e) => setRefillOn(e.target.checked)} />
          <span className="text-pretty">{t("money.refill.check")}</span>
        </label>
        {refillOn ? (
          <Field label={t("money.refill.amount", { currency: bagCurrency === "EUR" ? "€" : "USD" })} hint={t("money.refill.hint")} error={refillError ?? undefined} className="pl-6">
            {(a11y) => (
              <Input {...a11y} inputMode="decimal" autoComplete="off" value={refill} placeholder="0,00" className="max-w-40 tabular-nums" onChange={(e) => setRefill(e.target.value)} />
            )}
          </Field>
        ) : null}
        <label className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1 size-4 shrink-0 accent-primary" checked={alertLow} onChange={(e) => setAlertLow(e.target.checked)} />
          <span className="text-pretty">{t("money.alertLow")}</span>
        </label>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {error.text}
          {error.code === "bags_not_active" ? (
            <>
              {" "}
              <Link href={MIGRATION_HREF} className="font-medium underline underline-offset-4">
                {t("money.migration.cta")}
              </Link>
            </>
          ) : null}
        </p>
      ) : null}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          {t("money.cancel")}
        </Button>
        <Button type="submit" loading={busy} disabled={!canSubmit}>
          {t("money.assign.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── bajar: «Devolver a tu cuenta» ──────────────────────────────────────────

function LowerForm({ refId, name, ctx, actions, onClose }: { refId: string; name: string; ctx: BagContext; actions: AssignActions; onClose: () => void }) {
  const t = useT();
  const router = useRouter();
  const bag = ctx.bag.balance;
  const [value, setValue] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<{ text: string; code: string | null } | null>(null);
  const keyRef = React.useRef<{ micros: number; key: string } | null>(null);
  const parsed = parseAmount(value);
  const micros = parsed.kind === "ok" ? parsed.micros : 0;
  const tooMuch = micros > bag.amount_micros;
  const fieldError =
    parsed.kind === "invalid"
      ? t("money.amount.invalid")
      : parsed.kind === "ok" && micros <= 0
        ? t("money.amount.positive")
        : tooMuch
          ? t("money.error.bag_below_spent", { amount: moneyText(bag, "down") })
          : null;
  const eurUsd = ctx.eurUsd ? eurUsdOf(ctx.eurUsd.rate, "EUR", "USD") : null;
  const back = micros > 0 && !tooMuch && (bag.currency === ctx.available.currency || eurUsd != null)
    ? money(eurUsd != null ? convertMicros(micros, bag.currency, ctx.available.currency, eurUsd) : micros, ctx.available.currency)
    : null;
  const canSubmit = ctx.bagsActive && micros > 0 && !fieldError && !busy;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    if (!keyRef.current || keyRef.current.micros !== micros) keyRef.current = { micros, key: newIdempotencyKey("lower") };
    setBusy(true);
    setError(null);
    const res = await actions.lower({ ref: refId, amount: money(micros, bag.currency), key: keyRef.current.key });
    setBusy(false);
    if (res.ok) {
      toast.success(t("money.lower.done", { amount: moneyText(money(micros, bag.currency)), name, left: moneyText(res.data.balance, "down") }));
      onClose();
      router.refresh();
      return;
    }
    setError({ text: moneyErrorText(t, res, bag.currency), code: res.code ?? null });
  }

  if (bag.amount_micros <= 0) {
    return (
      <div className="grid gap-4">
        <p className="text-sm text-pretty text-muted-foreground">{t("money.lower.empty", { name })}</p>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("money.close")}
          </Button>
        </DialogFooter>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="lower-form">
      {!ctx.bagsActive ? <MigrationFirst t={t} /> : null}
      <Field
        label={t("money.lower.amount", { currency: bag.currency === "EUR" ? "€" : "USD" })}
        hint={t("money.lower.hint", { amount: moneyText(bag, "down") })}
        error={fieldError ?? undefined}
      >
        {(a11y) => (
          <Input {...a11y} inputMode="decimal" autoComplete="off" autoFocus value={value} placeholder="0,00" className="max-w-40 tabular-nums" onChange={(e) => setValue(e.target.value)} />
        )}
      </Field>
      <div role="status" aria-live="polite" aria-atomic="true" className="grid min-w-0 gap-1 rounded-md bg-muted/50 p-3 text-sm" data-slot="lower-receipt">
        <dl className="grid min-w-0 gap-1">
          <Row label={t("money.receipt.before", { name })} value={moneyText(bag, "down")} />
          <Row label={t("money.lower.after")} value={micros > 0 && !tooMuch ? moneyText(money(bag.amount_micros - micros, bag.currency), "down") : "—"} strong />
          <Row
            label={t("money.lower.back")}
            note={back && eurUsd != null ? fxLine(t, eurUsd, ctx.eurUsd?.date ?? null) : null}
            value={back ? moneyText(back) : "—"}
          />
        </dl>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {error.text}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          {t("money.cancel")}
        </Button>
        <Button type="submit" loading={busy} disabled={!canSubmit}>
          {t("money.lower.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── piezas ─────────────────────────────────────────────────────────────────

function MigrationFirst({ t }: { t: T }) {
  return (
    <Callout
      tone="info"
      title={t("money.migration.first.title")}
      action={
        <Button size="sm" nativeButton={false} render={<Link href={MIGRATION_HREF} />}>
          {t("money.migration.cta")}
        </Button>
      }
    >
      {t("money.migration.first.body")}
    </Callout>
  );
}

function Pill({ name, checked, onChange, children }: { name: string; checked: boolean; onChange: () => void; children: React.ReactNode }) {
  return (
    <label
      className={cn(
        "inline-flex h-8 cursor-pointer items-center rounded-full border px-3 text-sm font-medium tabular-nums has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
        checked ? "border-primary bg-primary text-primary-foreground" : "border-border bg-background hover:bg-muted",
      )}
    >
      <input type="radio" name={name} className="sr-only" checked={checked} onChange={onChange} />
      {children}
    </label>
  );
}

function Row({ label, value, note, strong }: { label: string; value: string; note?: string | null; strong?: boolean }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-3">
      <dt className="min-w-0 text-pretty text-muted-foreground">
        {label}
        {note ? <span className="block text-xs">{note}</span> : null}
      </dt>
      <dd className={cn("shrink-0 tabular-nums", strong && "font-semibold")}>{value}</dd>
    </div>
  );
}
