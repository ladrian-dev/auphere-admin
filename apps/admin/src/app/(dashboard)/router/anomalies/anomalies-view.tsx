import Link from "next/link";

import {
  Callout,
  EmptyState,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { RouterAnomalies } from "@/lib/backend-models";

import { ANOMALY_LABEL } from "../policy";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/**
 * Spec 047 (T150, 54.9): what Auphere has to look at — decisions that fell to
 * the reserve model or found no model in the client's residency — and who is
 * waiting in the Inbox for «Sin modelo disponible».
 */
export function AnomaliesView({ data }: { data: RouterAnomalies }) {
  const waiting = data.waiting_no_model.reduce((n, w) => n + w.conversations, 0);
  if (!data.items.length && !waiting) {
    return (
      <EmptyState
        title="Sin anomalías en este periodo"
        description="Ninguna decisión del router cayó en el modelo de reserva ni se quedó sin modelo."
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {waiting ? (
        <Callout tone="warning" title="Esperan a una persona por «Sin modelo disponible»">
          {waiting} conversaciones en la Bandeja:{" "}
          {data.waiting_no_model.map((w, i) => (
            <span key={w.tenant_id}>
              {i ? ", " : ""}
              <Link className="underline underline-offset-2" href={`/tenants/${w.tenant_id}`}>
                {w.tenant_name}
              </Link>{" "}
              ({w.conversations})
            </span>
          ))}
          .
        </Callout>
      ) : null}
      {data.items.length ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Cliente</TableHead>
              <TableHead>Tarea</TableHead>
              <TableHead>Anomalía</TableHead>
              <TableHead>Decisión</TableHead>
              <TableHead>Cuándo</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((a, i) => (
              <TableRow key={`${a.tenant_id}:${a.decision_id ?? i}:${a.created_at}`}>
                <TableCell>
                  <Link className="underline-offset-2 hover:underline" href={`/tenants/${a.tenant_id}`}>
                    {a.tenant_name}
                  </Link>
                </TableCell>
                <TableCell>
                  <code>{a.task}</code>
                </TableCell>
                <TableCell>
                  <StatusBadge tone={a.kind === "no_model" ? "danger" : "warning"}>
                    {ANOMALY_LABEL[a.kind] ?? a.kind}
                  </StatusBadge>
                </TableCell>
                <TableCell>
                  <code className="break-all text-xs text-muted-foreground">{a.decision_id ?? "—"}</code>
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm">{DATE.format(new Date(a.created_at))}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
      <p className="text-xs text-muted-foreground text-pretty">
        Los enfriamientos de un despliegue tras un fallo son de cada proceso del worker: van a su log
        («llm.cooldown»), no a esta lista.
      </p>
    </div>
  );
}
