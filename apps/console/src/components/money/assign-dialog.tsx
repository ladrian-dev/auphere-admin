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
  Label,
  Skeleton,
  Switch,
  cn,
  formatMoney,
} from "@nexus/ui";

import { assignBalanceAction, bagContextAction, lowerBalanceAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";
import type { BagContext, BagOut, Money, Receipt } from "@/lib/backend/money-types";

import { AmountOption } from "./amount-option";
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
 *   «Otra cantidad», que admite coma decimal. La elegida se marca con un
 *   tinte (spec 072 §6.1), y el botón dice el importe: «Asignar 20,00 USD».
 * - El recibo, anunciado (`role=status`), con una línea por dato (072 §6.3):
 *   su saldo ahora, lo que asignas, su nuevo saldo y lo que te queda en el
 *   tuyo. Si la cuenta va en otra moneda, lo que sale de ella y la línea del
 *   BCE van como nota de «Asignas»: es el mismo dinero, no otra cifra. Si no
 *   llega, «Faltan» en rojo, «Recargar mi cuenta» para quien compra, el botón
 *   desactivado y una línea que dice por qué (072 §6.2). Si la cuenta se queda
 *   con menos del 20 %, un aviso ámbar que no bloquea.
 * - «Rellenar cada mes hasta 35,50 USD», un interruptor que dice su importe
 *   (072 §6.5), y «Avisarme cuando le quede menos del 20 %», marcada por
 *   defecto.
 * - Mientras carga, un esqueleto con las mismas piezas: el diálogo tiene su
 *   alto final desde el primer fotograma (072 §6.4).
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
          <AssignSkeleton t={t} change={change} onClose={() => onOpenChange(false)} />
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
  // Lo que escribe la persona en «Hasta». Mientras no escriba, el relleno es
  // el que ya tenía la bolsa o, si no tenía, su nuevo saldo.
  const [refillTyped, setRefillTyped] = React.useState<string | null>(null);
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
  const refill =
    refillTyped ?? (ctx.bag.refill_up_to ? amountInputValue(ctx.bag.refill_up_to.amount_micros) : preview ? amountInputValue(preview.after.amount_micros) : "");
  const refillParsed = parseAmount(refill);
  const refillLabel =
    refillParsed.kind === "ok" && refillParsed.micros > 0
      ? t("money.refill.switch", { amount: moneyText(money(refillParsed.micros, bagCurrency)) })
      : t("money.refill.switchNoAmount");
  const refillError = refillOn && refillParsed.kind !== "ok" ? t("money.amount.invalid") : refillOn && refillParsed.kind === "ok" && refillParsed.micros <= 0 ? t("money.amount.positive") : null;
  const canSubmit = ctx.bagsActive && !noFx && micros > 0 && !amountError && !missing && !refillError && !busy;
  // Por qué el botón está apagado, cuando no lo dice ya otra cosa: el campo
  // con su error, el aviso de las bolsas o el del cambio (072 §6.2).
  const why = missing
    ? t("money.assign.why.short", { amount: moneyText(ctx.available, "down") })
    : choice.kind === "other" && parsed.kind === "empty"
      ? t("money.assign.why.amount")
      : null;
  const whyId = `${base}-why`;

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
            <AmountOption key={q} name={`${base}-amount`} checked={choice.kind === "quick" && choice.value === q} onChange={() => pick({ kind: "quick", value: q })}>
              {formatMoney(q, bagCurrency)}
            </AmountOption>
          ))}
          <AmountOption name={`${base}-amount`} checked={choice.kind === "other"} onChange={() => pick({ kind: "other" })}>
            {t("money.amount.other")}
          </AmountOption>
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
          <Row label={t("money.assign.receipt.now")} value={moneyText(ctx.bag.balance, "down")} />
          <Row
            label={t("money.assign.receipt.assigned")}
            note={
              preview?.eurUsd != null ? (
                <>
                  <span className="block">{t("money.assign.receipt.debit", { amount: moneyText(preview.debit) })}</span>
                  <span className="block">{fxLine(t, preview.eurUsd, ctx.eurUsd?.date ?? null)}</span>
                </>
              ) : null
            }
            value={preview ? moneyText(preview.assigned) : "—"}
          />
          <Row label={t("money.assign.receipt.after")} value={preview ? moneyText(preview.after, "down") : "—"} strong />
          <Row
            label={t("money.assign.receipt.left")}
            value={missing ? "—" : preview ? moneyText(preview.left, "down") : moneyText(ctx.available, "down")}
          />
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
        <div className="flex min-h-6 min-w-0 items-center gap-2" data-slot="assign-option">
          <Switch id={`${base}-refill`} checked={refillOn} onCheckedChange={(on) => setRefillOn(on === true)} />
          <Label htmlFor={`${base}-refill`} className="text-sm font-normal text-pretty">
            {refillLabel}
          </Label>
        </div>
        {refillOn ? (
          <Field label={t("money.refill.amount", { currency: bagCurrency === "EUR" ? "€" : "USD" })} hint={t("money.refill.hint")} error={refillError ?? undefined} className="pl-12">
            {(a11y) => (
              <Input {...a11y} inputMode="decimal" autoComplete="off" value={refill} placeholder="0,00" className="max-w-40 tabular-nums" onChange={(e) => setRefillTyped(e.target.value)} />
            )}
          </Field>
        ) : null}
        <label className="flex min-h-6 min-w-0 items-start gap-2 text-sm" data-slot="assign-option">
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

      {why && !canSubmit ? (
        <p id={whyId} className="text-sm text-pretty text-muted-foreground" data-slot="assign-why">
          {why}
        </p>
      ) : null}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          {t("money.cancel")}
        </Button>
        <Button type="submit" loading={busy} disabled={!canSubmit} aria-describedby={why && !canSubmit ? whyId : undefined}>
          {micros > 0 && !amountError ? t("money.assign.submitAmount", { amount: moneyText(money(micros, bagCurrency)) }) : t("money.assign.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * Mientras carga el contexto de la bolsa: las mismas piezas que el formulario
 * con sus mismos altos (los importes, el recibo de cuatro líneas, las dos
 * opciones y el pie), para que el diálogo no cambie de alto al llegar
 * (072 §6.4). La moneda aún no se sabe, así que no se inventa ninguna cifra.
 */
function AssignSkeleton({ t, change, onClose }: { t: T; change: boolean; onClose: () => void }) {
  return (
    <div className="grid min-w-0 gap-4" aria-busy="true" data-slot="assign-skeleton">
      <span role="status" className="sr-only">
        {t("money.loading")}
      </span>
      {/* «Subir» y «Devolver a tu cuenta», si es «Cambiar saldo». */}
      {change ? <Skeleton className="h-9 w-56 max-w-full" /> : null}
      <div className="grid min-w-0 gap-2">
        <Skeleton className="mb-1 h-5 w-16" />
        <div className="flex min-w-0 flex-wrap gap-2">
          {["w-20", "w-20", "w-20", "w-24", "w-28"].map((w, i) => (
            <Skeleton key={i} data-skeleton="pill" className={cn("h-8 rounded-full", w)} />
          ))}
        </div>
      </div>
      <div className="grid min-w-0 gap-2 rounded-md bg-muted/50 p-3">
        <Skeleton className="h-5 w-16" />
        <div className="grid min-w-0 gap-1">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} data-skeleton="row" className="flex min-w-0 items-center justify-between gap-3">
              <Skeleton className="h-5 w-32 max-w-full" />
              <Skeleton className="h-5 w-20" />
            </div>
          ))}
        </div>
      </div>
      <div className="grid min-w-0 gap-2">
        {[0, 1].map((i) => (
          <div key={i} data-skeleton="option" className="flex min-h-6 min-w-0 items-center gap-2">
            <Skeleton className="h-6 w-11 rounded-full" />
            <Skeleton className="h-5 w-56 max-w-full" />
          </div>
        ))}
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          {t("money.cancel")}
        </Button>
        <Button type="button" disabled>
          {t("money.assign.submit")}
        </Button>
      </DialogFooter>
    </div>
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

function Row({ label, value, note, strong }: { label: string; value: string; note?: React.ReactNode; strong?: boolean }) {
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
