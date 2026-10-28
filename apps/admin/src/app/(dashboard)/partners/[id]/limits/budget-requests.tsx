import { EmptyState, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@nexus/ui";
import type { BuildBudgetRequest } from "@/lib/backend-levers";
import { actorLabel } from "@/lib/levers";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/**
 * Spec 047 (T172, 46.5): the «Pedir ampliación» the partner sent when its
 * «Construcción y pruebas» ran out — one a day at most, the newest first.
 */
export function BudgetRequests({ requests }: { requests: BuildBudgetRequest[] }) {
  if (!requests.length) {
    return (
      <EmptyState
        readonly
        title="Nadie ha pedido ampliación"
        description="Cuando el partner agota «Construcción y pruebas», su consola le ofrece «Pedir ampliación» y la petición aparece aquí."
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Quién la pidió</TableHead>
          <TableHead>Cuándo</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {requests.map((r) => (
          <TableRow key={`${r.requested_by}:${r.created_at}`}>
            <TableCell className="text-sm" title={r.requested_by}>
              {actorLabel(r.requested_by)}
            </TableCell>
            <TableCell className="whitespace-nowrap text-sm">{DATE.format(new Date(r.created_at))} UTC</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
