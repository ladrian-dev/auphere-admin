import Link from "next/link";

import { EmptyState, StatusBadge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@nexus/ui";
import type { LedgerDiff, MetaDiff } from "@/lib/backend-levers";

import { ledgerExplain, metaExplain } from "./anomalies";

const DAY = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeZone: "UTC" });

/**
 * Spec 047 (T172; 43.9, 54.9): what does not add up in the money of the
 * partners that charge from bags — a bag whose balance is not the sum of its
 * entries, or an account whose ledger and transfers disagree. Computed now,
 * the same check as the daily cron.
 */
export function LedgerDiffs({ rows }: { rows: LedgerDiff[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        readonly
        title="El libro cuadra"
        description="Cada bolsa suma sus asientos y cada cuenta coincide con sus traspasos, al céntimo."
      />
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Partner</TableHead>
              <TableHead>Dónde</TableHead>
              <TableHead>Diferencia</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((d, i) => {
              const e = ledgerExplain(d);
              return (
                <TableRow key={`${d.partner_id}:${d.kind}:${d.kind === "bag" ? d.tenant_id : i}`}>
                  <TableCell>
                    <Link className="underline-offset-2 hover:underline" href={`/partners/${d.partner_id}/money`}>
                      {d.partner_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm">
                    {d.kind === "bag" ? (
                      <Link className="underline-offset-2 hover:underline" href={`/tenants/${d.tenant_id}`}>
                        {e.what}
                      </Link>
                    ) : (
                      e.what
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-pretty">{e.detail}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground text-pretty">
        Cada importe va en la moneda de su bolsa o de su cuenta. Solo se cuadran los partners con la consola nueva y las bolsas activas.
      </p>
    </div>
  );
}

/**
 * Spec 047 (T172; 2.6, 54.9): the days on which the messages Meta delivered
 * to a number were not the ones stored (`meta_reconciliation_runs`).
 */
export function MetaDiffs({ rows }: { rows: MetaDiff[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        readonly
        title="Meta y la base coinciden"
        description="Cada mensaje que Meta entregó en este periodo está guardado, y no hay ninguno de más."
      />
    );
  }
  return (
    <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Día</TableHead>
            <TableHead>Cliente</TableHead>
            <TableHead>Número</TableHead>
            <TableHead className="text-right">Meta</TableHead>
            <TableHead className="text-right">Guardados</TableHead>
            <TableHead>Diferencia</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={`${r.channel_id}:${r.date}`}>
              <TableCell className="whitespace-nowrap text-sm">{DAY.format(new Date(`${r.date}T00:00:00Z`))}</TableCell>
              <TableCell>
                <Link className="underline-offset-2 hover:underline" href={`/tenants/${r.tenant_id}`}>
                  {r.tenant_name}
                </Link>
              </TableCell>
              <TableCell>
                <Link
                  className="font-mono text-sm underline-offset-2 hover:underline"
                  href={`/tenants/${r.tenant_id}/channels/${r.channel_id}`}
                >
                  {r.identifier ?? "Canal sin número"}
                </Link>
              </TableCell>
              <TableCell className="text-right text-sm tabular-nums">{r.meta_count}</TableCell>
              <TableCell className="text-right text-sm tabular-nums">{r.stored_count}</TableCell>
              <TableCell>
                <StatusBadge tone={r.diff > 0 ? "danger" : "warning"}>{metaExplain(r)}</StatusBadge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
