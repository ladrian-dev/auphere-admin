"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { TenantPaymentMethod, TenantPaymentOut } from "@/lib/backend";

import {
  recordTenantPaymentAction,
  voidTenantPaymentAction,
} from "../../actions";

const SELECT_CLASS =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm";

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

function usd(cents: number): string {
  return (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Mensualidades cobradas fuera del proveedor de pagos. Anotar una deja
 * constancia y nada más: no cambia el servicio del cliente.
 */
export function PaymentsCard({
  tenantId,
  payments,
  monthlyCents,
}: {
  tenantId: string;
  payments: TenantPaymentOut[];
  /** Lo que el cliente paga al mes; rellena el monto del formulario. */
  monthlyCents: number | null;
}) {
  const router = useRouter();
  const now = new Date();
  const [year, setYear] = useState(String(now.getFullYear()));
  const [month, setMonth] = useState(String(now.getMonth() + 1));
  const [amount, setAmount] = useState(
    monthlyCents ? (monthlyCents / 100).toFixed(2) : "",
  );
  const [method, setMethod] = useState<TenantPaymentMethod>("transfer");
  const [reference, setReference] = useState("");
  const [paidOn, setPaidOn] = useState(today());
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmVoid, setConfirmVoid] = useState<string | null>(null);
  const [voiding, setVoiding] = useState(false);

  async function onRecord() {
    const cents = Math.round(Number(amount) * 100);
    if (!amount.trim() || !Number.isFinite(cents) || cents <= 0) {
      toast.error("Escribe el monto recibido, mayor que cero");
      return;
    }
    if (!paidOn) {
      toast.error("Indica el día en que llegó el pago");
      return;
    }
    setSaving(true);
    try {
      const result = await recordTenantPaymentAction(tenantId, {
        period_year: Number(year),
        period_month: Number(month),
        amount_cents: cents,
        method,
        reference: reference.trim() || null,
        paid_on: paidOn,
        note: note.trim() || null,
      });
      if (!result.ok) {
        toast.error("No se pudo anotar el pago", { description: result.error });
        return;
      }
      toast.success(
        `Pago de ${MONTHS[result.data.period_month - 1]} ${result.data.period_year} anotado`,
      );
      setReference("");
      setNote("");
      router.refresh();
    } finally {
      setSaving(false);
    }
  }

  async function onVoid(paymentId: string) {
    setVoiding(true);
    try {
      const result = await voidTenantPaymentAction(tenantId, paymentId);
      if (!result.ok) {
        toast.error("No se pudo anular", { description: result.error });
        return;
      }
      toast.success("Pago anulado");
      setConfirmVoid(null);
      router.refresh();
    } finally {
      setVoiding(false);
    }
  }

  return (
    <div className="grid gap-6">
      {payments.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
          Aún no hay pagos anotados para este cliente.
        </div>
      ) : (
        <div className="rounded-md border border-border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mes</TableHead>
                <TableHead className="text-right">Monto</TableHead>
                <TableHead>Medio</TableHead>
                <TableHead className="hidden md:table-cell">
                  Referencia
                </TableHead>
                <TableHead className="hidden sm:table-cell">Recibido</TableHead>
                <TableHead className="hidden lg:table-cell">Anotó</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right" aria-label="Acciones" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.map((p) => {
                const voided = p.voided_at != null;
                return (
                  <TableRow
                    key={p.id}
                    className={voided ? "text-muted-foreground" : undefined}
                  >
                    <TableCell className="font-medium">
                      {MONTHS[p.period_month - 1]} {p.period_year}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {usd(p.amount_cents)}
                    </TableCell>
                    <TableCell>{METHOD_LABEL[p.method] ?? p.method}</TableCell>
                    <TableCell className="hidden md:table-cell">
                      {p.reference ? (
                        <code className="text-xs">{p.reference}</code>
                      ) : (
                        "—"
                      )}
                      {p.note ? (
                        <span className="block text-xs text-muted-foreground">
                          {p.note}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell tabular-nums">
                      {p.paid_on}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-xs">
                      {p.recorded_by}
                    </TableCell>
                    <TableCell>
                      <Badge variant={voided ? "outline" : "secondary"}>
                        {voided ? "Anulado" : "Pagado"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      {voided ? null : confirmVoid === p.id ? (
                        <span className="inline-flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={voiding}
                            onClick={() => onVoid(p.id)}
                          >
                            {voiding ? "Anulando…" : "Sí, anular"}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={voiding}
                            onClick={() => setConfirmVoid(null)}
                          >
                            No
                          </Button>
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirmVoid(p.id)}
                        >
                          Anular
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="grid gap-4 max-w-2xl">
        <h3 className="text-sm font-medium">Anotar un pago</h3>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="grid gap-2 text-sm">
            <span className="text-muted-foreground">Mes que cubre</span>
            <select
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className={SELECT_CLASS}
            >
              {MONTHS.map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm">
            <span className="text-muted-foreground">Año</span>
            <Input
              value={year}
              onChange={(e) => setYear(e.target.value)}
              inputMode="numeric"
            />
          </label>
          <label className="grid gap-2 text-sm">
            <span className="text-muted-foreground">Monto recibido (USD)</span>
            <Input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="decimal"
              placeholder="75.00"
            />
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
            <Input
              type="date"
              value={paidOn}
              onChange={(e) => setPaidOn(e.target.value)}
            />
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
        <div>
          <Button onClick={onRecord} disabled={saving}>
            {saving ? "Anotando…" : "Anotar pago"}
          </Button>
        </div>
      </div>
    </div>
  );
}
