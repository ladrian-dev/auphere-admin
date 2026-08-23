import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
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

import { RechargeWalletForm } from "./recharge-form";

function fmt(n: number): string {
  return n.toLocaleString("es-ES");
}

/**
 * Consumo C3 del partner — included / purchased / available / reserve.
 * Recarga purchased (staging). Sin caps de cliente. Sin tool Companion.
 */
export default async function PartnerWalletPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, wallet, ledger] = await Promise.all([
    backend.getPartner(id),
    backend.getPartnerWallet(id),
    backend.listPartnerWalletLedger(id),
  ]);
  if (!partner || !wallet) notFound();

  const summary = [
    { label: "Included", value: fmt(wallet.included_remaining) },
    { label: "Purchased", value: fmt(wallet.purchased_remaining) },
    { label: "Available", value: fmt(wallet.available) },
    { label: "Reserve", value: fmt(wallet.reserve) },
  ] as const;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Consumo</Eyebrow>
          <CardTitle>Bolsa C3 del partner</CardTitle>
          <CardDescription>
            Saldo included (caduca) y purchased (recarga admin). Reserve es
            available menos la suma de caps. No hay tope por cliente desde
            este panel.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4">
            {summary.map((item) => (
              <div key={item.label}>
                <dt className="text-xs text-muted-foreground">{item.label}</dt>
                <dd className="text-lg font-medium tabular-nums">{item.value}</dd>
              </div>
            ))}
          </dl>
          {wallet.exhausted ? (
            <p className="text-sm text-muted-foreground">La bolsa está agotada.</p>
          ) : null}
          <RechargeWalletForm partnerId={partner.id} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Ledger</Eyebrow>
          <CardTitle>Últimos asientos</CardTitle>
          <CardDescription>
            Débitos y recargas purchased. Sin filas de allocation de cliente.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {ledger.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Aún no hay asientos en el libro de este partner.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cuándo</TableHead>
                    <TableHead>Cubo</TableHead>
                    <TableHead>Motivo</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ledger.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="font-mono text-xs">
                        {new Date(row.created_at).toLocaleString("es-ES")}
                      </TableCell>
                      <TableCell>{row.bucket}</TableCell>
                      <TableCell>{row.reason}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(row.qty)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
