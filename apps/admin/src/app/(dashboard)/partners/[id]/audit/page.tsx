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
import { fullDateTime } from "@/lib/format";

const AUDIT_LIMIT = 100;

/**
 * Timeline read-only del embed audit (key.created, key.rotated,
 * session.minted, broadcast.sent…). Últimas 100 entradas, más reciente
 * primero. El payload completo se expande por fila.
 */
export default async function PartnerAuditPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, entries] = await Promise.all([
    backend.getPartner(id),
    backend.listPartnerAudit(id, AUDIT_LIMIT),
  ]);
  if (!partner) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Auditoría</Eyebrow>
          <CardTitle>Actividad del embed</CardTitle>
          <CardDescription>
            Cada mint de session token, creación/rotación/revocación de key
            y cambio de origins queda registrado. Solo lectura — últimas{" "}
            {AUDIT_LIMIT} entradas.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {entries.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Sin actividad registrada todavía. Las entradas aparecen en
              cuanto el partner use sus keys.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Evento</TableHead>
                    <TableHead>Fecha</TableHead>
                    <TableHead className="hidden md:table-cell">IP</TableHead>
                    <TableHead className="hidden md:table-cell">
                      Origin
                    </TableHead>
                    <TableHead className="hidden lg:table-cell">JTI</TableHead>
                    <TableHead>Payload</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map((entry) => {
                    const hasPayload =
                      entry.payload && Object.keys(entry.payload).length > 0;
                    return (
                      <TableRow key={entry.id}>
                        <TableCell>
                          <Badge variant="outline" className="font-mono">
                            {entry.event}
                          </Badge>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-muted-foreground tabular-nums">
                          {fullDateTime(entry.created_at)}
                        </TableCell>
                        <TableCell className="hidden md:table-cell font-mono text-xs text-muted-foreground">
                          {entry.ip ?? "—"}
                        </TableCell>
                        <TableCell className="hidden md:table-cell font-mono text-xs text-muted-foreground max-w-48 truncate">
                          <span title={entry.origin ?? undefined}>
                            {entry.origin ?? "—"}
                          </span>
                        </TableCell>
                        <TableCell className="hidden lg:table-cell font-mono text-xs text-muted-foreground">
                          {entry.jti ? (
                            <span title={entry.jti}>
                              {entry.jti.slice(0, 8)}…
                            </span>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell>
                          {hasPayload ? (
                            <details className="group">
                              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground transition-colors select-none">
                                Ver payload
                              </summary>
                              <pre className="mt-2 max-w-md overflow-x-auto rounded-md border border-border bg-muted/40 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all">
                                {JSON.stringify(entry.payload, null, 2)}
                              </pre>
                            </details>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              —
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
        </CardContent>
      </Card>
    </div>
  );
}
