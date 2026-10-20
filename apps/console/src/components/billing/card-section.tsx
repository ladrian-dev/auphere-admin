"use client";

import { CreditCard } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Alert,
  AlertDescription,
  Button,
  ConfirmDialog,
  Input,
  Label,
  StatusBadge,
  formatCurrency,
  formatDate,
} from "@nexus/ui";

import { deleteCardAction, setChargingAction, startCardAction } from "@/app/(console)/billing/actions";
import { useLocale, useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { BillingCardView } from "@/lib/backend";

type Mode = BillingCardView["mode"];

const CHARGE_TONE = { paid: "positive", pending: "info", action_required: "warning", failed: "danger" } as const;

/**
 * Spec 041: the partner's card on Stripe and how it is charged — by hand, an
 * automatic top-up below a threshold, or postpaid on the 1st (only with the
 * credit line Auphere grants). The card is entered on Stripe's page: its
 * number never reaches Auphere.
 */
export function CardSection({ view, canManage, justSaved }: { view: BillingCardView; canManage: boolean; justSaved: boolean }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, start] = React.useTransition();
  const [mode, setMode] = React.useState<Mode>(view.mode);
  const [threshold, setThreshold] = React.useState(String((view.recharge_threshold_cents ?? 1000) / 100));
  const [amount, setAmount] = React.useState(String((view.recharge_amount_cents ?? 2000) / 100));
  const [confirmRemove, setConfirmRemove] = React.useState(false);
  const money = (cents: number) => formatCurrency(cents / 100, "USD", locale);
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
    const key = `card.error.${res.code ?? ""}`;
    const known = ["card_required", "no_credit_line", "amount_too_small", "threshold_required"];
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

  return (
    <section aria-labelledby="card-h" className="flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="card-h" className="text-lg font-semibold">
          {t("card.title")}
        </h2>
        <p className="text-sm text-pretty text-muted-foreground">{t("card.help")}</p>
      </div>

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

      <div className="flex flex-wrap items-center gap-3 rounded-md p-4 ring-1 ring-foreground/10">
        <CreditCard className="size-5 text-muted-foreground" aria-hidden="true" />
        <span className="min-w-0 flex-1 text-sm">
          {view.card
            ? view.card.last4
              ? t("card.saved", {
                  brand: (view.card.brand ?? "").toUpperCase(),
                  last4: view.card.last4,
                  month: String(view.card.exp_month ?? "").padStart(2, "0"),
                  year: String(view.card.exp_year ?? ""),
                })
              : // Not every saved method is a card (Link has no last 4 digits).
                t("card.savedOther", { method: methodName(view.card.brand) })
            : t("card.none")}
        </span>
        {canManage ? (
          <span className="flex gap-2">
            <Button variant={view.card ? "outline" : "default"} onClick={openStripe} disabled={pending}>
              {view.card ? t("card.replace") : t("card.add")}
            </Button>
            {view.card ? (
              <Button variant="ghost" onClick={() => setConfirmRemove(true)} disabled={pending}>
                {t("card.remove")}
              </Button>
            ) : null}
          </span>
        ) : null}
      </div>

      <fieldset className="flex flex-col gap-3" disabled={!canManage || pending}>
        <legend className="mb-2 text-sm font-medium">{t("card.mode")}</legend>
        {(["manual", "auto_recharge", "postpaid"] as const).map((m) => {
          const locked = (m !== "manual" && !view.card) || (m === "postpaid" && !hasLine);
          return (
            <label key={m} className="flex items-start gap-3 text-sm">
              <input
                type="radio"
                name="charging-mode"
                value={m}
                checked={mode === m}
                disabled={locked}
                onChange={() => setMode(m)}
                className="mt-1"
              />
              <span className={locked ? "text-muted-foreground" : undefined}>
                {t(`card.mode.${m}`)}
                {m === "postpaid" ? (
                  <span className="block text-xs text-muted-foreground">
                    {hasLine
                      ? t("card.mode.postpaid.line", { limit: money(view.credit_limit_cents), owed: money(view.owed_cents) })
                      : t("card.mode.postpaid.locked")}
                  </span>
                ) : null}
              </span>
            </label>
          );
        })}
        {!view.card ? <p className="text-xs text-muted-foreground">{t("card.needsCard")}</p> : null}
        {mode === "auto_recharge" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="threshold">{t("card.threshold")}</Label>
              <Input id="threshold" type="number" min={0} step={1} value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="amount">{t("card.amount")}</Label>
              <Input id="amount" type="number" min={5} step={1} value={amount} onChange={(e) => setAmount(e.target.value)} />
              <span className="text-xs text-muted-foreground">{t("card.amount.min")}</span>
            </div>
          </div>
        ) : null}
        {canManage ? (
          <div>
            <Button onClick={save} disabled={!dirty || pending}>
              {pending ? t("card.saving") : t("card.save")}
            </Button>
          </div>
        ) : null}
      </fieldset>

      {view.charges.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">{t("card.charges")}</h3>
          <ul className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
            {view.charges.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <span>
                  {c.kind === "postpaid" ? t("card.charge.postpaid", { period: c.period ?? "" }) : t("card.charge.auto_recharge")}
                  <span className="text-muted-foreground"> · {formatDate(c.created_at, locale)}</span>
                </span>
                <span className="flex items-center gap-3">
                  <span className="tabular-nums">{money(c.amount_cents)}</span>
                  <StatusBadge tone={CHARGE_TONE[c.status]}>{t(`card.charge.${c.status}`)}</StatusBadge>
                  {c.status === "action_required" && c.action_url && canManage ? (
                    <Button size="sm" nativeButton={false} render={<a href={c.action_url} target="_blank" rel="noreferrer" />}>
                      {t("card.charge.confirm")}
                    </Button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

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
    </section>
  );
}
