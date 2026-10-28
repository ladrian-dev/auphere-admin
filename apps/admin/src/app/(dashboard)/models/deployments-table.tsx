import {
  Badge,
  EmptyState,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { DeploymentRow } from "@/lib/backend-models";

import { ActivateDialog, PriceDialog, RetireDialog, UnavailableDialog } from "./deployment-dialogs";
import { RESIDENCY_LABEL, STATUS_LABEL, STATUS_TONE, formatPrice } from "./labels";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeZone: "UTC" });

/**
 * Spec 047 (T150): one row per deployment — what it is, where it runs, what it
 * costs today, where it is certified and what it still lacks — with the
 * operator's writes at the end of the row. Costs are shown as they are: this
 * is the only surface that shows them (54.11).
 */
export function DeploymentsTable({ rows }: { rows: DeploymentRow[] }) {
  if (!rows.length) {
    return (
      <EmptyState readonly
        title="Ningún despliegue con este estado"
        description="Un despliegue nuevo entra en borrador desde «Nuevo despliegue»."
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Despliegue</TableHead>
          <TableHead>Proveedor y ruta</TableHead>
          <TableHead>Residencia</TableHead>
          <TableHead>Estado</TableHead>
          <TableHead>Precio vigente</TableHead>
          <TableHead>Certificado en</TableHead>
          <TableHead>Le falta</TableHead>
          <TableHead>
            <span className="sr-only">Acciones</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const d = row.deployment;
          const servable = d.status === "active" || d.status === "retiring";
          return (
            <TableRow key={row.uuid}>
              <TableCell className="max-w-64 align-top">
                <div className="flex min-w-0 flex-col">
                  <span className="truncate font-medium">{row.display_name ?? d.id}</span>
                  <code className="break-all text-xs text-muted-foreground">{d.id}</code>
                </div>
              </TableCell>
              <TableCell className="align-top">
                <div className="flex min-w-0 flex-col text-sm">
                  <span>{d.provider}</span>
                  <span className="break-all text-xs text-muted-foreground">
                    {[d.route, d.region].filter(Boolean).join(" · ") || "—"}
                  </span>
                </div>
              </TableCell>
              <TableCell className="align-top">{RESIDENCY_LABEL[d.residency]}</TableCell>
              <TableCell className="align-top">
                <div className="flex flex-col gap-1">
                  <StatusBadge tone={STATUS_TONE[d.status]}>{STATUS_LABEL[d.status]}</StatusBadge>
                  {d.retire_after ? (
                    <span className="text-xs text-muted-foreground">Hasta el {DATE.format(new Date(d.retire_after))}</span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="min-w-40 align-top text-sm">{formatPrice(row.current_price)}</TableCell>
              <TableCell className="align-top">
                {row.certified_tasks.length ? (
                  <div className="flex flex-wrap gap-1">
                    {row.certified_tasks.map((t) => (
                      <Badge key={t} variant="outline">
                        {t}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <span className="text-sm text-muted-foreground">Ninguna tarea</span>
                )}
              </TableCell>
              <TableCell className="max-w-72 align-top text-sm">
                {row.activation_missing.length ? (
                  <ul className="list-disc pl-4 text-pretty">
                    {Object.values(row.activation_messages).map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-muted-foreground">Nada</span>
                )}
              </TableCell>
              <TableCell className="align-top">
                <div className="flex flex-wrap justify-end gap-2">
                  {d.status !== "active" && d.status !== "retired" && d.status !== "retiring" ? (
                    <ActivateDialog row={row} />
                  ) : null}
                  <PriceDialog row={row} />
                  {servable && d.status !== "retiring" ? <RetireDialog row={row} /> : null}
                  {d.status !== "unavailable" && d.status !== "retired" ? <UnavailableDialog row={row} /> : null}
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
