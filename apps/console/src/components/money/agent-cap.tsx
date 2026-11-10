"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, Field, Input } from "@nexus/ui";

import { setAgentCapAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";
import type { AgentCapOut, Currency, Money } from "@/lib/backend/money-types";

import { amountInputValue, money, moneyErrorText, moneyText, parseAmount, type Failed } from "./money-model";

type Result<T> = { ok: true; data: T } | Failed;
export type CapActions = { save: (body: { ref: string; agent: string; cap: Money | null }) => Promise<Result<AgentCapOut>> };
const SERVER: CapActions = { save: (b) => setAgentCapAction(b) };

/**
 * El tope mensual de un agente (spec 047, requisito 44.1): en la moneda de la
 * bolsa de su cliente, por mes natural en UTC. Al 80 % avisa; al 100 % el agente
 * se pausa («Pausado · tope del agente») hasta el mes siguiente o hasta que se
 * suba. Puede pasar de lo que hay en la bolsa (44.4). Es la única cosa que se
 * llama «tope» en la consola (45.6).
 *
 * `cap` en `undefined` es que no se sabe el de hoy: se dice, en vez de enseñar
 * un campo vacío que parezca «sin tope».
 */
export function AgentCapForm({
  refId,
  agentId,
  agentName,
  cap,
  spent = null,
  currency,
  canWrite,
  onSaved,
  actions = SERVER,
}: {
  refId: string;
  agentId: string;
  agentName: string;
  cap: Money | null | undefined;
  /** Lo gastado este mes (UTC), si se sabe. */
  spent?: Money | null;
  currency: Currency;
  canWrite: boolean;
  onSaved?: (cap: Money | null) => void;
  actions?: CapActions;
}) {
  const t = useT();
  const router = useRouter();
  const [current, setCurrent] = React.useState(cap);
  const [value, setValue] = React.useState(cap ? amountInputValue(cap.amount_micros) : "");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const parsed = parseAmount(value);
  const fieldError = parsed.kind === "invalid" ? t("money.amount.invalid") : parsed.kind === "ok" && parsed.micros <= 0 ? t("money.amount.positive") : null;
  const sym = currency === "EUR" ? "€" : "USD";

  async function save(next: Money | null) {
    setBusy(true);
    setError(null);
    const res = await actions.save({ ref: refId, agent: agentId, cap: next });
    setBusy(false);
    if (!res.ok) {
      setError(moneyErrorText(t, res, currency));
      return;
    }
    const saved = res.data.monthly_cap_micros != null ? money(res.data.monthly_cap_micros, currency) : null;
    setCurrent(saved);
    setValue(saved ? amountInputValue(saved.amount_micros) : "");
    toast.success(saved ? t("money.cap.saved", { name: agentName, amount: moneyText(saved) }) : t("money.cap.removed", { name: agentName }));
    onSaved?.(saved);
    router.refresh();
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (parsed.kind === "empty") return void save(null);
    if (parsed.kind !== "ok" || fieldError) return;
    void save(money(parsed.micros, currency));
  }

  const base =
    current === undefined ? t("money.cap.unknown") : current ? t("money.cap.current", { amount: moneyText(current) }) : t("money.cap.none");
  const now = spent ? `${base} ${t("money.cap.spent", { amount: moneyText(spent) })}` : base;

  if (!canWrite) {
    return (
      <p className="text-sm text-pretty" data-slot="agent-cap">
        {now}
      </p>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-3" data-slot="agent-cap">
      <p className="text-sm text-pretty text-muted-foreground">{now}</p>
      <Field label={t("money.cap.label", { currency: sym })} hint={t("money.cap.hint", { currency })} error={(fieldError ?? error) || undefined}>
        {(a11y) => (
          <Input {...a11y} inputMode="decimal" autoComplete="off" value={value} placeholder={t("money.cap.placeholder")} className="max-w-40 tabular-nums" onChange={(e) => setValue(e.target.value)} />
        )}
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" loading={busy} disabled={Boolean(fieldError) || (parsed.kind === "empty" && !current)}>
          {t("money.cap.save")}
        </Button>
        {current ? (
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void save(null)}>
            {t("money.cap.remove")}
          </Button>
        ) : null}
      </div>
    </form>
  );
}

/** El tope desde la fila del agente en el Panel del cliente (44.1). */
export function AgentCapButton(props: Omit<React.ComponentProps<typeof AgentCapForm>, "onSaved">) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const [cap, setCap] = React.useState(props.cap);
  return (
    <>
      <Button type="button" variant="link" size="xs" className="h-auto p-0" onClick={() => setOpen(true)} aria-label={t("money.cap.edit.aria", { name: props.agentName })}>
        {cap ? moneyText(cap) : cap === null ? t("money.cap.noneShort") : t("money.cap.set")}
      </Button>
      {open ? (
        <Dialog open onOpenChange={setOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t("money.cap.title", { name: props.agentName })}</DialogTitle>
              <DialogDescription>{t("money.cap.body")}</DialogDescription>
            </DialogHeader>
            <AgentCapForm
              {...props}
              cap={cap}
              onSaved={(saved) => {
                setCap(saved);
                setOpen(false);
              }}
            />
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}
