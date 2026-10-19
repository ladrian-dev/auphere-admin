import { CreditCard } from "lucide-react";

import { DescriptionList, Section, StatusBadge } from "@nexus/ui";

import { backend } from "@/lib/backend";
import { formatCents, fullDateTime } from "@/lib/format";

import { ChargingForm } from "./charging-form";
import { CreditLimitForm } from "./credit-limit-form";

const MODE_LABEL = {
  manual: "Manual (compra saldo a mano)",
  auto_recharge: "Recarga automática",
  postpaid: "Pospago (se cobra el día 1)",
} as const;
const CHARGE_TONE = { paid: "positive", pending: "info", action_required: "warning", failed: "danger" } as const;
const CHARGE_LABEL = {
  paid: "Pagado",
  pending: "En curso",
  action_required: "Falta que el partner lo confirme (3D Secure)",
  failed: "Rechazado",
} as const;

/**
 * Spec 041: the partner's card (brand and last four — Auphere never sees
 * more), how it is charged, its charges, and the postpaid line, which is
 * Auphere's decision.
 */
export default async function BillingCard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const view = await backend.getPartnerBilling(id).catch(() => null);
  if (!view) {
    return (
      <Section title="Tarjeta y cobro automático">
        <p className="text-sm text-muted-foreground">No se pudo leer la tarjeta del partner.</p>
      </Section>
    );
  }
  return (
    <Section
      title="Tarjeta y cobro automático"
      description="La tarjeta la guarda el partner en la página de Stripe desde su consola. Cómo se le cobra lo puede elegir él o Auphere desde aquí; la línea de crédito del pospago solo la concede Auphere."
    >
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-3 text-sm">
          <CreditCard className="size-5 text-muted-foreground" aria-hidden="true" />
          {view.card ? (
            <span>
              {(view.card.brand ?? "").toUpperCase()} terminada en {view.card.last4} · caduca{" "}
              {String(view.card.exp_month ?? "").padStart(2, "0")}/{view.card.exp_year}
              {view.card.saved_at ? (
                <span className="text-muted-foreground"> · guardada el {fullDateTime(view.card.saved_at)}</span>
              ) : null}
            </span>
          ) : (
            <span className="text-muted-foreground">
              Sin tarjeta guardada. El partner la añade desde Facturación en su consola.
            </span>
          )}
        </div>
        <DescriptionList
          columns={3}
          items={[
            { key: "mode", term: "Cómo se cobra", detail: MODE_LABEL[view.mode] },
            {
              key: "rule",
              term: "Regla de recarga",
              detail:
                view.mode === "auto_recharge"
                  ? `${formatCents(view.recharge_amount_cents)} si baja de ${formatCents(view.recharge_threshold_cents)}`
                  : "—",
            },
            {
              key: "state",
              term: "Estado",
              detail: view.credit_frozen ? (
                <span className="text-status-danger-text">Línea congelada: un cobro del pospago no se completó</span>
              ) : view.paused_reason ? (
                <span className="text-status-danger-text">Parado: {view.paused_reason}</span>
              ) : view.failed_attempts > 0 ? (
                `${view.failed_attempts} intento(s) fallido(s)`
              ) : (
                "En orden"
              ),
            },
            { key: "line", term: "Línea de crédito", detail: formatCents(view.credit_limit_cents) },
            { key: "owed", term: "Debe ahora", detail: formatCents(view.owed_cents) },
          ]}
        />
        <ChargingForm
          partnerId={id}
          current={{ mode: view.mode, threshold: view.recharge_threshold_cents, amount: view.recharge_amount_cents }}
          hasCard={view.card !== null}
          hasLine={view.credit_limit_cents > 0}
        />
        <CreditLimitForm partnerId={id} currentCents={view.credit_limit_cents} owedCents={view.owed_cents} />
        {view.charges.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">Cobros a la tarjeta</h3>
            <ul className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
              {view.charges.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span>
                    {c.kind === "postpaid" ? `Consumo de ${c.period}` : "Recarga automática"}
                    <span className="text-muted-foreground"> · {fullDateTime(c.created_at)}</span>
                    {c.failure_code ? (
                      <span className="text-status-danger-text"> · {c.failure_code}</span>
                    ) : null}
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="tabular-nums">{formatCents(c.amount_cents)}</span>
                    <StatusBadge tone={CHARGE_TONE[c.status]}>{CHARGE_LABEL[c.status]}</StatusBadge>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Section>
  );
}
