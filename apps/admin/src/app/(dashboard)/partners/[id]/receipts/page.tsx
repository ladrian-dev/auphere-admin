import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { backend } from "@/lib/backend";

import { GenerateReceiptForm, ResendReceiptButton } from "./receipts-client";

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

const STATUS_LABEL: Record<string, string> = {
  draft: "Borrador",
  issued: "Emitido",
  paid: "Pagado",
  void: "Anulado",
};

function usd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/**
 * Recibos mensuales del partner. Cada recibo suma los cargos de sus
 * tenants (comisión 2,5% de ventas WhatsApp convertida a USD al dólar
 * observado del día de emisión, suscripciones e inactivos) en un total
 * único. Corte 1→fin de mes, emisión el día 1, vencimiento el día 5.
 */
export default async function PartnerReceiptsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, receipts] = await Promise.all([
    backend.getPartner(id),
    backend.listPartnerReceipts(id),
  ]);
  if (!partner) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Recibos</Eyebrow>
          <CardTitle>Recibos mensuales</CardTitle>
          <CardDescription>
            Total en USD a cobrar al partner por mes. Comisión 2,5% de las
            ventas WhatsApp (convertida al dólar observado del día de emisión)
            más suscripciones. Correo a{" "}
            {partner.billing_email ? (
              <code>{partner.billing_email}</code>
            ) : (
              <span className="text-muted-foreground">
                (sin correo de facturación configurado)
              </span>
            )}
            .
          </CardDescription>
        </CardHeader>
        <CardContent>
          {receipts.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Aún no hay recibos. Genera el del mes anterior con el formulario
              de abajo, o espera al barrido automático del día 1.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Periodo</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead className="hidden sm:table-cell">Vence</TableHead>
                    <TableHead className="text-right">Correo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {receipts.map((r) => (
                    <TableRow key={r.invoice_id}>
                      <TableCell className="font-medium">
                        {MONTHS[r.period_month - 1]} {r.period_year}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {usd(r.total_usd)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {STATUS_LABEL[r.status] ?? r.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden sm:table-cell text-muted-foreground tabular-nums">
                        {r.due_date}
                      </TableCell>
                      <TableCell className="text-right">
                        <ResendReceiptButton
                          partnerId={partner.id}
                          invoiceId={r.invoice_id}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Generar</Eyebrow>
          <CardTitle>Emitir recibo de un mes</CardTitle>
          <CardDescription>
            Idempotente: si ya existe el recibo de ese periodo, se devuelve el
            existente sin duplicar. Por defecto apunta al mes anterior.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <GenerateReceiptForm partnerId={partner.id} />
        </CardContent>
      </Card>
    </div>
  );
}
