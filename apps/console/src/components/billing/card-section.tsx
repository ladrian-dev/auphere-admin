"use client";

import { CreditCard, Receipt, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  ConfirmDialog,
  Input,
  Label,
  StatusBadge,
  cn,
  formatCurrency,
  formatDate,
} from "@nexus/ui";

import { deleteCardAction, setChargingAction, startCardAction } from "@/app/(console)/billing/actions";
import { useLocale, useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { BillingCardView } from "@/lib/backend";

import { CHECKOUT_CURRENCY } from "./buy-credit-form";

type Mode = BillingCardView["mode"];

const CHARGE_TONE = { paid: "positive", pending: "info", action_required: "warning", failed: "danger" } as const;
/** La recarga mínima que acepta la API (`amount_too_small`), en céntimos de la moneda del cobro. */
const MIN_RECHARGE_CENTS = 500;

/**
 * Spec 041: the partner's card on Stripe and how it is charged — by hand, an
 * automatic top-up below a threshold, or postpaid on the 1st (only with the
 * credit line Auphere grants). The card is entered on Stripe's page: its
 * number never reaches Auphere.
 *
 * Spec 047 (prototipo «Consola de partners v2»): una tarjeta con la tarjeta
 * guardada («Cambiar», «Quitar»), los tres modos en opciones con su
 * descripción y «Guardar». Los cobros van aparte, en `CardCharges`. Las cifras
 * salen de `Intl` con la moneda del cobro (Stripe cobra en `CHECKOUT_CURRENCY`).
 */
export function CardSection({
  view,
  canManage,
  justSaved,
  invoiceMissing = false,
}: {
  view: BillingCardView;
  canManage: boolean;
  justSaved: boolean;
  /** Back from «Ver factura» without an invoice to show. */
  invoiceMissing?: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, start] = React.useTransition();
  const [mode, setMode] = React.useState<Mode>(view.mode);
  const [threshold, setThreshold] = React.useState(String((view.recharge_threshold_cents ?? 1000) / 100));
  const [amount, setAmount] = React.useState(String((view.recharge_amount_cents ?? 2000) / 100));
  const [confirmRemove, setConfirmRemove] = React.useState(false);
  const money = (cents: number) => formatCurrency(cents / 100, CHECKOUT_CURRENCY, locale);
  const hasLine = view.credit_limit_cents > 0;

  function errorText(res: {
    ok: false;
    status: number;
    message: string;
    code?: string | null;
    info?: Record<string, unknown>;
  }) {
    // Stripe's own reason, so a refused call is not a bare «could not reach the server».
    if (res.code === "billing_provider_error") {
      const reason = String(res.info?.message ?? res.info?.provider_code ?? "");
      return t("card.error.provider", { reason });
    }
    if (res.code === "billing_unavailable") return t("card.error.unavailable");
    if (res.code === "amount_too_small") return t("proto.billing.amount.min", { amount: money(MIN_RECHARGE_CENTS) });
    const key = `card.error.${res.code ?? ""}`;
    const known = ["card_required", "no_credit_line", "threshold_required"];
    return known.includes(res.code ?? "") ? t(key as "card.error.card_required") : actionErrorText(res, t);
  }

  function methodName(brand: string | null): string {
    if (!brand) return t("card.method.unknown");
    if (brand === "link") return "Link";
    return brand.toUpperCase();
  }

  function openStripe() {
    start(async () => {
      const res = await startCardAction();
      if (!res.ok) return void toast.error(errorText(res));
      if (res.data.url) window.location.assign(res.data.url);
    });
  }

  function save() {
    start(async () => {
      const res = await setChargingAction({
        mode,
        recharge_threshold_cents: mode === "auto_recharge" ? Math.round(Number(threshold) * 100) : null,
        recharge_amount_cents: mode === "auto_recharge" ? Math.round(Number(amount) * 100) : null,
      });
      if (!res.ok) return void toast.error(errorText(res));
      toast.success(t("card.saveDone"));
      router.refresh();
    });
  }

  const dirty =
    mode !== view.mode ||
    (mode === "auto_recharge" &&
      (Math.round(Number(threshold) * 100) !== view.recharge_threshold_cents ||
        Math.round(Number(amount) * 100) !== view.recharge_amount_cents));

  const modes = (["manual", "auto_recharge", "postpaid"] as const).map((m) => ({
    mode: m,
    locked: (m !== "manual" && !view.card) || (m === "postpaid" && !hasLine),
    hint:
      m === "postpaid" && hasLine
        ? t("card.mode.postpaid.line", { limit: money(view.credit_limit_cents), owed: money(view.owed_cents) })
        : t(`proto.billing.mode.${m}.hint`),
  }));

  return (
    <Card aria-labelledby="card-h" role="region" data-slot="billing-card">
      <CardContent className="flex min-w-0 flex-col gap-4">
        <div className="grid gap-1">
          <h2 id="card-h" className="text-base font-semibold">
            {t("card.title")}
          </h2>
          <p className="text-sm text-pretty text-muted-foreground">{t("card.help")}</p>
        </div>

        {invoiceMissing ? (
          <Alert>
            <AlertDescription>{t("card.charge.invoiceMissing")}</AlertDescription>
          </Alert>
        ) : null}
        {justSaved && !view.card ? (
          <Alert>
            <AlertDescription>{t("card.justSaved")}</AlertDescription>
          </Alert>
        ) : null}
        {view.charges.some((c) => c.status === "action_required" && c.action_url) ? (
          <Alert>
            <AlertDescription>{t("card.actionRequired")}</AlertDescription>
          </Alert>
        ) : null}
        {view.credit_frozen ? (
          <Alert variant="destructive">
            <AlertDescription>{t("card.frozen")}</AlertDescription>
          </Alert>
        ) : null}
        {view.paused_reason ? (
          <Alert variant="destructive">
            <AlertDescription>{t("card.paused")}</AlertDescription>
          </Alert>
        ) : null}

        {/* La tarjeta guardada (`.cardbox`): el método, la caducidad y sus dos botones. */}
        <div className="flex min-w-0 flex-wrap items-center gap-3 rounded-lg p-4 ring-1 ring-foreground/10" data-slot="billing-cardbox">
          <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
            <CreditCard className="size-4" />
          </span>
          {view.card ? (
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-sm font-medium">
                {view.card.last4
                  ? t("proto.billing.card.endsIn", { brand: (view.card.brand ?? "").toUpperCase(), last4: view.card.last4 })
                  : // Not every saved method is a card (Link has no last 4 digits).
                    t("card.savedOther", { method: methodName(view.card.brand) })}
              </span>
              {view.card.exp_month && view.card.exp_year ? (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {t("proto.billing.card.expires", { month: String(view.card.exp_month).padStart(2, "0"), year: String(view.card.exp_year) })}
                </span>
              ) : null}
            </span>
          ) : (
            <span className="min-w-0 flex-1 text-sm text-muted-foreground">{t("card.none")}</span>
          )}
          {canManage ? (
            <span className="flex gap-2">
              {view.card ? (
                <>
                  <Button variant="outline" size="sm" onClick={openStripe} disabled={pending}>
                    {t("proto.billing.card.change")}
                  </Button>
                  <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => setConfirmRemove(true)} disabled={pending}>
                    {t("proto.billing.card.remove")}
                  </Button>
                </>
              ) : (
                <Button size="sm" onClick={openStripe} disabled={pending}>
                  {t("card.add")}
                </Button>
              )}
            </span>
          ) : null}
        </div>

        {/* Los modos en opciones (`.radio`): nombre, descripción y el elegido con borde primario. */}
        <fieldset className="flex min-w-0 flex-col gap-2" disabled={!canManage || pending}>
          <legend className="sr-only">{t("card.mode")}</legend>
          <div role="radiogroup" aria-label={t("card.mode")} className="flex min-w-0 flex-col gap-2">
            {modes.map(({ mode: m, locked, hint }) => (
              <React.Fragment key={m}>
                <label
                  className={cn(
                    "flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-input bg-card p-3 text-sm transition-colors",
                    mode === m && "border-primary ring-1 ring-primary",
                    locked && "cursor-not-allowed opacity-60",
                  )}
                >
                  <input
                    type="radio"
                    name="charging-mode"
                    value={m}
                    checked={mode === m}
                    disabled={locked}
                    onChange={() => setMode(m)}
                    className="mt-1 size-4 shrink-0 accent-primary"
                  />
                  <span className="flex min-w-0 flex-col">
                    <span className="font-medium">{t(`proto.billing.mode.${m}`)}</span>
                    <span className="text-pretty text-muted-foreground">{hint}</span>
                  </span>
                </label>
                {m === "auto_recharge" && mode === "auto_recharge" ? (
                  <div className="grid gap-3 pl-8 sm:grid-cols-2" data-slot="billing-recharge">
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="threshold">{t("proto.billing.threshold")}</Label>
                      <Input id="threshold" type="number" min={0} step={1} value={threshold} onChange={(e) => setThreshold(e.target.value)} />
                    </div>
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="amount">{t("proto.billing.amount")}</Label>
                      <Input id="amount" type="number" min={MIN_RECHARGE_CENTS / 100} step={1} value={amount} onChange={(e) => setAmount(e.target.value)} />
                    </div>
                    <p className="text-xs text-muted-foreground sm:col-span-2">{t("proto.billing.amount.min", { amount: money(MIN_RECHARGE_CENTS) })}</p>
                  </div>
                ) : null}
              </React.Fragment>
            ))}
          </div>
          {!view.card ? <p className="text-xs text-muted-foreground">{t("card.needsCard")}</p> : null}
          {canManage ? (
            <div className="pt-2">
              <Button size="sm" onClick={save} disabled={!dirty || pending}>
                {pending ? t("card.saving") : t("card.save")}
              </Button>
            </div>
          ) : null}
        </fieldset>
      </CardContent>

      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title={t("card.remove.title")}
        description={t("card.remove.body")}
        confirmLabel={t("card.remove")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={async () => {
          const res = await deleteCardAction();
          if (!res.ok) return void toast.error(errorText(res));
          setConfirmRemove(false);
          setMode("manual");
          router.refresh();
        }}
      />
    </Card>
  );
}

/**
 * «Cobros a la tarjeta» (prototipo): su propia tarjeta, una fila por cobro con
 * su baldosa —recarga o consumo—, la fecha, el importe, el estado en palabras y
 * «Confirmar el pago» o «Ver factura».
 */
export function CardCharges({ view, canManage }: { view: BillingCardView; canManage: boolean }) {
  const t = useT();
  const locale = useLocale();
  if (view.charges.length === 0) return null;
  const money = (cents: number) => formatCurrency(cents / 100, CHECKOUT_CURRENCY, locale);
  return (
    <Card aria-labelledby="charges-h" role="region" data-slot="billing-charges">
      <CardContent className="grid min-w-0 gap-2">
        <h2 id="charges-h" className="text-base font-semibold">
          {t("card.charges")}
        </h2>
        <ul className="-mx-4 divide-y divide-border">
          {view.charges.map((c) => {
            const Icon = c.kind === "postpaid" ? Receipt : RotateCcw;
            return (
              <li key={c.id} className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
                  <Icon className="size-4" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="font-medium">{c.kind === "postpaid" ? t("card.charge.postpaid", { period: c.period ?? "" }) : t("card.charge.auto_recharge")}</span>
                  <span className="text-xs text-muted-foreground">{formatDate(c.created_at, locale)}</span>
                </span>
                <span className="font-medium tabular-nums">{money(c.amount_cents)}</span>
                <StatusBadge tone={CHARGE_TONE[c.status]}>{t(`card.charge.${c.status}`)}</StatusBadge>
                {c.status === "action_required" && c.action_url && canManage ? (
                  <Button size="sm" nativeButton={false} render={<a href={c.action_url} target="_blank" rel="noreferrer" />}>
                    {t("card.charge.confirm")}
                  </Button>
                ) : c.has_invoice ? (
                  <Button size="sm" variant="ghost" nativeButton={false} render={<a href={`/api/billing/charges/${c.id}/invoice`} target="_blank" rel="noreferrer" />}>
                    {t("card.charge.invoice")}
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
