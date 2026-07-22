"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { generateReceiptAction, sendReceiptAction } from "../../actions";

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

/** Previous calendar month — the default period a receipt covers. */
function previousMonth(): { year: number; month: number } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + 1; // 1-based
  return m === 1 ? { year: y - 1, month: 12 } : { year: y, month: m - 1 };
}

export function GenerateReceiptForm({ partnerId }: { partnerId: string }) {
  const router = useRouter();
  const initial = previousMonth();
  const [year, setYear] = useState(String(initial.year));
  const [month, setMonth] = useState(String(initial.month));
  const [sendEmail, setSendEmail] = useState(true);
  const [busy, setBusy] = useState(false);

  async function onGenerate() {
    setBusy(true);
    try {
      const result = await generateReceiptAction(partnerId, {
        period_year: Number(year),
        period_month: Number(month),
        send_email: sendEmail,
      });
      if (!result.ok) {
        toast.error("No se pudo generar el recibo", {
          description: result.error,
        });
        return;
      }
      const r = result.data;
      const total = r.total_usd.toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
      });
      toast.success(
        r.created
          ? `Recibo generado — ${total}`
          : `El recibo de ${MONTHS[r.period_month - 1]} ${r.period_year} ya existía — ${total}`,
      );
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-[1fr_1fr_auto_auto] md:items-end">
      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">Mes</span>
        <select
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
        >
          {MONTHS.map((name, i) => (
            <option key={name} value={i + 1}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">Año</span>
        <Input
          value={year}
          onChange={(e) => setYear(e.target.value)}
          inputMode="numeric"
          className="font-mono"
        />
      </label>
      <label className="flex items-center gap-2 text-sm md:pb-2">
        <input
          type="checkbox"
          checked={sendEmail}
          onChange={(e) => setSendEmail(e.target.checked)}
          className="size-4"
        />
        Enviar por correo
      </label>
      <Button onClick={onGenerate} disabled={busy}>
        {busy ? "Generando…" : "Generar recibo"}
      </Button>
    </div>
  );
}

export function ResendReceiptButton({
  partnerId,
  invoiceId,
}: {
  partnerId: string;
  invoiceId: string;
}) {
  const [busy, setBusy] = useState(false);

  async function onResend() {
    setBusy(true);
    try {
      const result = await sendReceiptAction(partnerId, invoiceId);
      if (!result.ok) {
        toast.error("No se pudo enviar", { description: result.error });
        return;
      }
      toast[result.data.emailed ? "success" : "warning"](
        result.data.emailed
          ? `Enviado a ${result.data.to}`
          : "Correo no configurado (revisa NEXUS_RESEND_API_KEY)",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant="ghost" size="sm" onClick={onResend} disabled={busy}>
      {busy ? "Enviando…" : "Reenviar"}
    </Button>
  );
}
