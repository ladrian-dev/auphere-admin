import { CheckCircle2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Eyebrow,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";

import { backend } from "@/lib/backend";
import { formatCents, fullDateTime } from "@/lib/format";
import { LEDGER_KIND_LABEL, isCredit } from "@/lib/money";

import { RechargeWalletForm } from "./recharge-form";

/** Spec 004 (R7.2): the operator sees the figures, never a proportion. */
function fmt(cents: number): string {
  return formatCents(cents);
}

/**
 * Spec 033 — the partner's money, in US$. Recharged balance (what the
 * clients' turns spend), the weekly pool (Companion and teammates), what the
 * clients have as monthly caps, whether the book balances, and the entries.
 */
export default async function PartnerWalletPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [partner, wallet, ledger, reconcile] = await Promise.all([
    backend.getPartner(id),
    backend.getPartnerWallet(id),
    backend.listPartnerWalletLedger(id),
    backend.getPartnerWalletReconcile(id).catch(() => null),
  ]);
  if (!partner || !wallet) notFound();

  const summary = [
    { label: "Saldo recargado", value: fmt(wallet.purchased_cents), hint: "Lo que gastan los turnos de sus clientes" },
    { label: "Pool semanal", value: fmt(wallet.included_cents), hint: "Companion y teammates; se repone cada semana" },
    { label: "Asignado a clientes", value: fmt(wallet.assigned_cents), hint: "Suma de los topes mensuales" },
  ] as const;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Dinero</Eyebrow>
          <CardTitle>Saldo del partner</CardTitle>
          <CardDescription>
            Todo en US$. El partner reparte el saldo recargado entre sus clientes con un tope mensual por cliente.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-3">
            {summary.map((item) => (
              <div key={item.label} className="flex flex-col gap-1">
                <dt className="text-xs text-muted-foreground">{item.label}</dt>
                <dd className="text-xl font-semibold tabular-nums">{item.value}</dd>
                <dd className="text-xs text-muted-foreground">{item.hint}</dd>
              </div>
            ))}
          </dl>
          {wallet.exhausted ? (
            <p className="text-sm text-status-warning-text">
              Sin saldo recargado: sus clientes no responden hasta que haya saldo.
            </p>
          ) : null}
          {/* R7.2 (spec 004): the absolute figures, for diagnosis. */}
          <span className="sr-only">
            {fmt(wallet.included_cents)} · {fmt(wallet.purchased_cents)}
          </span>
          <RechargeWalletForm partnerId={partner.id} purchasedCents={wallet.purchased_cents} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Conciliación</Eyebrow>
          <CardTitle>¿Cuadra el libro?</CardTitle>
          <CardDescription>
            Saldo recargado guardado frente a recargas − gastos − caducidades del libro.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {reconcile === null ? (
            <p className="text-sm text-status-warning-text">No se pudo leer el libro ahora mismo.</p>
          ) : reconcile.balanced ? (
            <p className="flex items-center gap-2 text-sm">
              <CheckCircle2 aria-hidden="true" className="size-4 text-status-positive" />
              El libro cuadra: {fmt(reconcile.credits_cents)} recargados − {fmt(reconcile.debits_cents)} gastados −{" "}
              {fmt(reconcile.expiries_cents)} caducados = {fmt(reconcile.stored_cents)}.
            </p>
          ) : (
            <p className="flex items-center gap-2 text-sm text-destructive" role="alert">
              <TriangleAlert aria-hidden="true" className="size-4" />
              El libro no cuadra: guardado {fmt(reconcile.stored_cents)}, según el libro {fmt(reconcile.expected_cents)} (diferencia de{" "}
              {reconcile.difference_credits.toLocaleString("es")} créditos). Revisa la auditoría antes de recargar.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Libro</Eyebrow>
          <CardTitle>Últimos movimientos</CardTitle>
          <CardDescription>Recargas, gastos y caducidades, del más reciente al más antiguo.</CardDescription>
        </CardHeader>
        <CardContent>
          {ledger.length === 0 ? (
            <EmptyState title="Aún no hay movimientos" description="La primera recarga aparecerá aquí." readonly />
          ) : (
            <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cuándo</TableHead>
                    <TableHead>Movimiento</TableHead>
                    <TableHead className="hidden md:table-cell">Cliente</TableHead>
                    <TableHead className="hidden sm:table-cell">Bolsillo</TableHead>
                    <TableHead className="text-right">Importe</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ledger.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="text-sm text-muted-foreground tabular-nums">{fullDateTime(row.created_at)}</TableCell>
                      <TableCell className="text-sm">{LEDGER_KIND_LABEL[row.kind] ?? row.kind}</TableCell>
                      <TableCell className="hidden md:table-cell text-sm">
                        {row.tenant_id ? (
                          <Link href={`/tenants/${row.tenant_id}`} className="underline-offset-4 hover:underline">
                            {row.client_name ?? "Cliente"}
                          </Link>
                        ) : (
                          <span className="text-muted-foreground">{row.kind === "debit" ? "Companion" : "—"}</span>
                        )}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                        {row.bucket === "purchased" ? "Recargado" : "Pool semanal"}
                      </TableCell>
                      <TableCell
                        className={
                          isCredit(row.kind)
                            ? "text-right font-medium text-status-positive-text tabular-nums"
                            : "text-right tabular-nums"
                        }
                      >
                        {isCredit(row.kind) ? "+" : "−"}
                        {fmt(row.amount_cents)}
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
