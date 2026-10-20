"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Input, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@nexus/ui";

import type { PartnerPaymentOut, TenantPaymentMethod } from "@/lib/backend";
import { formatCents } from "@/lib/format";

import { creditPartnerPaymentAction, recordPartnerPaymentAction, voidPartnerPaymentAction } from "../../actions";

const SELECT_CLASS = "h-9 rounded-md border border-input bg-transparent px-3 text-sm";

const MONTHS = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

const METHOD_LABEL: Record<TenantPaymentMethod, string> = {
  transfer: "Transferencia",
  cash: "Efectivo",
  zelle: "Zelle",
  paypal: "PayPal",
  crypto: "Cripto",
  other: "Otro",
};

/** Before this day, recording a payment credited nothing (owner's call). */
const CREDIT_SINCE = "2026-10-20";

function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

type Client = { tenantId: string; name: string; monthlyCents: number | null };

function creditLabel(p: PartnerPaymentOut): { text: string; tone: "positive" | "muted" | "warning" } {
  if (p.credited_cents != null) {
    return { text: `+${formatCents(p.credited_cents)} al saldo`, tone: p.voided_at ? "muted" : "positive" };
  }
  if (p.created_at.slice(0, 10) < CREDIT_SINCE) return { text: "Anterior al abono automático", tone: "muted" };
  return { text: "Sin abonar", tone: "warning" };
}

export function PartnerPaymentsClient({
  partnerId,
  payments,
  clients,
}: {
  partnerId: string;
  payments: PartnerPaymentOut[];
  clients: Client[];
}) {
  const router = useRouter();
  const now = new Date();
  const [tenantId, setTenantId] = useState(clients[0]?.tenantId ?? "");
  const [year, setYear] = useState(String(now.getFullYear()));
  const [month, setMonth] = useState(String(now.getMonth() + 1));
  const monthly = (id: string) => clients.find((c) => c.tenantId === id)?.monthlyCents ?? null;
  const [amount, setAmount] = useState(() => {
    const m = monthly(clients[0]?.tenantId ?? "");
    return m ? (m / 100).toFixed(2) : "";
  });
  const [method, setMethod] = useState<TenantPaymentMethod>("transfer");
  const [reference, setReference] = useState("");
  const [paidOn, setPaidOn] = useState(today());
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmVoid, setConfirmVoid] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function onRecord() {
    const cents = Math.round(Number(amount.replace(",", ".")) * 100);
    if (!tenantId) return void toast.error("Elige el cliente del pago");
    if (!amount.trim() || !Number.isFinite(cents) || cents <= 0) {
      return void toast.error("Escribe el monto recibido, mayor que cero");
    }
    if (!paidOn) return void toast.error("Indica el día en que llegó el pago");
    setSaving(true);
    try {
      const result = await recordPartnerPaymentAction(partnerId, {
        tenant_id: tenantId,
        period_year: Number(year),
        period_month: Number(month),
        amount_cents: cents,
        method,
        reference: reference.trim() || null,
        paid_on: paidOn,
        note: note.trim() || null,
      });
      if (!result.ok) return void toast.error("No se pudo anotar el pago", { description: result.error });
      const credited = result.data.credited_cents;
      toast.success(
        credited != null
          ? `Pago anotado: ${formatCents(credited)} sumados al saldo del partner`
          : "Pago anotado, pero no se pudo abonar el saldo. Pulsa «Abonar» en la fila.",
      );
      setReference("");
      setNote("");
      router.refresh();
    } finally {
      setSaving(false);
    }
  }

  async function onVoid(paymentId: string) {
    setBusy(paymentId);
    try {
      const result = await voidPartnerPaymentAction(partnerId, paymentId);
      if (!result.ok) return void toast.error("No se pudo anular", { description: result.error });
      toast.success("Pago anulado y descontado del saldo");
      setConfirmVoid(null);
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  async function onCredit(paymentId: string) {
    setBusy(paymentId);
    try {
      const result = await creditPartnerPaymentAction(partnerId, paymentId);
      if (!result.ok) return void toast.error("No se pudo abonar", { description: result.error });
      toast.success("Saldo abonado");
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  if (clients.length === 0 && payments.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Este partner aún no tiene clientes. Los pagos se anotan por cliente y mes.
      </p>
    );
  }

  return (
    <div className="grid gap-6">
      {payments.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
          Aún no hay pagos anotados para este partner.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cliente</TableHead>
                <TableHead>Mes</TableHead>
                <TableHead className="text-right">Monto</TableHead>
                <TableHead className="hidden sm:table-cell">Medio</TableHead>
                <TableHead className="hidden md:table-cell">Referencia</TableHead>
                <TableHead className="hidden sm:table-cell">Recibido</TableHead>
                <TableHead>Saldo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right" aria-label="Acciones" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.map((p) => {
                const voided = p.voided_at != null;
                const credit = creditLabel(p);
                return (
                  <TableRow key={p.id} className={voided ? "text-muted-foreground" : undefined}>
                    <TableCell className="font-medium">{p.client_name ?? "—"}</TableCell>
                    <TableCell>
                      {MONTHS[p.period_month - 1]} {p.period_year}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatCents(p.amount_cents)}</TableCell>
                    <TableCell className="hidden sm:table-cell">{METHOD_LABEL[p.method] ?? p.method}</TableCell>
                    <TableCell className="hidden md:table-cell">
                      {p.reference ? <code className="text-xs">{p.reference}</code> : "—"}
                      {p.note ? <span className="block text-xs text-muted-foreground">{p.note}</span> : null}
                    </TableCell>
                    <TableCell className="hidden tabular-nums sm:table-cell">{p.paid_on}</TableCell>
                    <TableCell
                      className={
                        credit.tone === "positive"
                          ? "text-status-success-text text-xs"
                          : credit.tone === "warning"
                            ? "text-status-warning-text text-xs"
                            : "text-xs text-muted-foreground"
                      }
                    >
                      {credit.text}
                    </TableCell>
                    <TableCell>
                      <Badge variant={voided ? "outline" : "secondary"}>{voided ? "Anulado" : "Pagado"}</Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right">
                      {voided ? null : confirmVoid === p.id ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="hidden text-xs text-muted-foreground lg:inline">
                            {p.credited_cents != null ? `Descuenta ${formatCents(p.credited_cents)}` : null}
                          </span>
                          <Button size="sm" variant="destructive" disabled={busy === p.id} onClick={() => onVoid(p.id)}>
                            {busy === p.id ? "Anulando…" : "Sí, anular"}
                          </Button>
                          <Button size="sm" variant="ghost" disabled={busy === p.id} onClick={() => setConfirmVoid(null)}>
                            No
                          </Button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          {credit.tone === "warning" ? (
                            <Button size="sm" variant="outline" disabled={busy === p.id} onClick={() => onCredit(p.id)}>
                              Abonar
                            </Button>
                          ) : null}
                          <Button size="sm" variant="ghost" onClick={() => setConfirmVoid(p.id)}>
                            Anular
                          </Button>
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {clients.length > 0 ? (
        <div className="grid max-w-2xl gap-4">
          <h3 className="text-sm font-medium">Anotar un pago</h3>
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="grid gap-2 text-sm sm:col-span-3">
              <span className="text-muted-foreground">Cliente que cubre</span>
              <select
                value={tenantId}
                onChange={(e) => {
                  setTenantId(e.target.value);
                  const m = monthly(e.target.value);
                  if (m) setAmount((m / 100).toFixed(2));
                }}
                className={SELECT_CLASS}
              >
                {clients.map((c) => (
                  <option key={c.tenantId} value={c.tenantId}>
                    {c.name}
                    {c.monthlyCents ? ` · ${formatCents(c.monthlyCents)}/mes` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-muted-foreground">Mes que cubre</span>
              <select value={month} onChange={(e) => setMonth(e.target.value)} className={SELECT_CLASS}>
                {MONTHS.map((name, i) => (
                  <option key={name} value={i + 1}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-muted-foreground">Año</span>
              <Input value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" />
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-muted-foreground">Monto recibido (US$)</span>
              <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="75.00" />
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-muted-foreground">Medio</span>
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as TenantPaymentMethod)}
                className={SELECT_CLASS}
              >
                {Object.entries(METHOD_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-muted-foreground">Día en que llegó</span>
              <Input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-muted-foreground">Referencia (opcional)</span>
              <Input
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                maxLength={120}
                placeholder="N.º de operación"
              />
            </label>
          </div>
          <label className="grid gap-2 text-sm">
            <span className="text-muted-foreground">Nota (opcional)</span>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              placeholder="Banco, quién transfirió, lo que ayude a encontrarlo después"
            />
          </label>
          <p className="text-xs text-muted-foreground">Al anotarlo, el monto se suma al saldo recargado del partner.</p>
          <div>
            <Button onClick={onRecord} disabled={saving}>
              {saving ? "Anotando…" : "Anotar pago"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
