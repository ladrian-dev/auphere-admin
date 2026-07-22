"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type {
  BillingPlanOut,
  PartnerOut,
  TenantBillingOut,
} from "@/lib/backend";

import {
  createBillingPlanAction,
  updateTenantBillingAction,
} from "../../actions";

const SELECT_CLASS =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm";

function centsToDollars(cents: number | null): string {
  return cents == null ? "" : (cents / 100).toFixed(2);
}

function dollarsToCents(v: string): number | null {
  const t = v.trim();
  if (t === "") return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

export function BillingForm({
  tenantId,
  billing,
  partners,
  plans,
}: {
  tenantId: string;
  billing: TenantBillingOut;
  partners: PartnerOut[];
  plans: BillingPlanOut[];
}) {
  const router = useRouter();
  const [partnerId, setPartnerId] = useState(billing.partner_id ?? "");
  const [planId, setPlanId] = useState(billing.billing_plan_id ?? "");
  const [override, setOverride] = useState(
    centsToDollars(billing.price_override_cents),
  );
  const [effectiveFrom, setEffectiveFrom] = useState(
    billing.billing_effective_from ?? "",
  );
  const [saving, setSaving] = useState(false);

  // Inline "create plan"
  const [showNewPlan, setShowNewPlan] = useState(false);
  const [planCode, setPlanCode] = useState("");
  const [planName, setPlanName] = useState("");
  const [planAmount, setPlanAmount] = useState("");
  const [creatingPlan, setCreatingPlan] = useState(false);

  async function onSave() {
    setSaving(true);
    try {
      const result = await updateTenantBillingAction(tenantId, {
        partner_id: partnerId || null,
        billing_plan_id: planId || null,
        price_override_cents: dollarsToCents(override),
        billing_effective_from: effectiveFrom || null,
      });
      if (!result.ok) {
        toast.error("No se pudo guardar", { description: result.error });
        return;
      }
      toast.success("Facturación actualizada");
      router.refresh();
    } finally {
      setSaving(false);
    }
  }

  async function onCreatePlan() {
    const cents = dollarsToCents(planAmount);
    if (!planCode.trim() || !planName.trim() || cents == null) {
      toast.error("Completa código, nombre y monto del plan");
      return;
    }
    setCreatingPlan(true);
    try {
      const result = await createBillingPlanAction({
        code: planCode.trim(),
        name: planName.trim(),
        monthly_amount_cents: cents,
      });
      if (!result.ok) {
        toast.error("No se pudo crear el plan", { description: result.error });
        return;
      }
      toast.success(`Plan "${result.data.name}" creado`);
      setPlanId(result.data.id); // select the fresh plan
      setShowNewPlan(false);
      setPlanCode("");
      setPlanName("");
      setPlanAmount("");
      router.refresh();
    } finally {
      setCreatingPlan(false);
    }
  }

  return (
    <div className="grid gap-5 max-w-xl">
      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">Partner</span>
        <select
          value={partnerId}
          onChange={(e) => setPartnerId(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Auphere (directo — sin partner)</option>
          {partners.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>

      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">Plan de suscripción</span>
        <select
          value={planId}
          onChange={(e) => setPlanId(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Sin plan (comisión o inactivo)</option>
          {plans.map((pl) => (
            <option key={pl.id} value={pl.id}>
              {pl.name} — ${(pl.monthly_amount_cents / 100).toFixed(2)}/mes
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setShowNewPlan((v) => !v)}
          className="justify-self-start text-xs text-muted-foreground underline hover:text-foreground"
        >
          {showNewPlan ? "Cancelar" : "+ Crear plan nuevo"}
        </button>
      </label>

      {showNewPlan && (
        <div className="grid gap-3 rounded-md border border-border p-3 md:grid-cols-[1fr_1.4fr_0.8fr_auto] md:items-end">
          <label className="grid gap-1 text-xs">
            <span className="text-muted-foreground">Código</span>
            <Input
              value={planCode}
              onChange={(e) => setPlanCode(e.target.value)}
              placeholder="amacrux_sub_75_usd"
              className="font-mono"
            />
          </label>
          <label className="grid gap-1 text-xs">
            <span className="text-muted-foreground">Nombre</span>
            <Input
              value={planName}
              onChange={(e) => setPlanName(e.target.value)}
              placeholder="Suscripción $75/mes"
            />
          </label>
          <label className="grid gap-1 text-xs">
            <span className="text-muted-foreground">USD/mes</span>
            <Input
              value={planAmount}
              onChange={(e) => setPlanAmount(e.target.value)}
              inputMode="decimal"
              placeholder="75"
            />
          </label>
          <Button size="sm" onClick={onCreatePlan} disabled={creatingPlan}>
            {creatingPlan ? "Creando…" : "Crear"}
          </Button>
        </div>
      )}

      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">
          Precio negociado (USD/mes, opcional)
        </span>
        <Input
          value={override}
          onChange={(e) => setOverride(e.target.value)}
          inputMode="decimal"
          placeholder="Deja vacío para usar el precio del plan"
        />
        <span className="text-xs text-muted-foreground">
          Si lo pones, este monto gana sobre el precio del plan.
        </span>
      </label>

      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">
          Inicio de facturación (opcional)
        </span>
        <Input
          type="date"
          value={effectiveFrom}
          onChange={(e) => setEffectiveFrom(e.target.value)}
        />
        <span className="text-xs text-muted-foreground">
          Primer mes que se cobra la suscripción. Vacío = desde el inicio.
        </span>
      </label>

      <div>
        <Button onClick={onSave} disabled={saving}>
          {saving ? "Guardando…" : "Guardar facturación"}
        </Button>
      </div>
    </div>
  );
}
