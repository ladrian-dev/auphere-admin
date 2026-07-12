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

const WINDOW_DAYS = 30;

/**
 * Vista de uso por partner — la base de métricas y facturación. Una fila
 * por cliente (negocio) del partner: estado, agente clonado, WhatsApp,
 * broadcasts, mensajes y costo de modelo en la ventana.
 */
export default async function PartnerUsagePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, usage] = await Promise.all([
    backend.getPartner(id),
    backend.getPartnerUsage(id, WINDOW_DAYS),
  ]);
  if (!partner || !usage) notFound();

  const summary = [
    { label: "Clientes", value: usage.clients_total },
    { label: "Activos", value: usage.clients_active },
    { label: "Con WhatsApp", value: usage.clients_whatsapp_connected },
    { label: "Con agente", value: usage.clients_with_agent },
    { label: "Broadcasts", value: usage.broadcasts },
    { label: "Destinatarios", value: usage.broadcast_recipients },
    { label: "Msgs entrantes", value: usage.messages_inbound },
    { label: "Msgs salientes", value: usage.messages_outbound },
    { label: "Costo modelo", value: `$${usage.cost_usd.toFixed(4)}` },
  ] as const;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Uso</Eyebrow>
          <CardTitle>Últimos {usage.window_days} días</CardTitle>
          <CardDescription>
            Consumo agregado de los clientes del partner — la vista para
            métricas y facturación. El costo es el gasto de modelo de los
            agentes de sus tenants.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-3 gap-x-6 gap-y-4 md:grid-cols-5 lg:grid-cols-9">
            {summary.map((item) => (
              <div key={item.label}>
                <dt className="text-xs text-muted-foreground">{item.label}</dt>
                <dd className="text-lg font-medium tabular-nums">
                  {item.value}
                </dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Clientes</Eyebrow>
          <CardTitle>Detalle por negocio</CardTitle>
          <CardDescription>
            Cada fila es un cliente final del partner (un tenant aislado).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {usage.clients.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              El partner aún no provisionó clientes. Aparecen en cuanto
              llame a POST /v1/partners/clients.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>WhatsApp</TableHead>
                    <TableHead>Agente</TableHead>
                    <TableHead className="text-right">Broadcasts</TableHead>
                    <TableHead className="text-right hidden md:table-cell">
                      Destinatarios
                    </TableHead>
                    <TableHead className="text-right hidden md:table-cell">
                      Msgs in/out
                    </TableHead>
                    <TableHead className="text-right">Costo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usage.clients.map((client) => (
                    <TableRow key={client.external_client_ref}>
                      <TableCell>
                        <div className="font-medium">
                          {client.client_name ?? "—"}
                        </div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {client.external_client_ref}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            client.tenant_status === "active"
                              ? "default"
                              : "secondary"
                          }
                        >
                          {client.tenant_status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {client.whatsapp_connected ? (
                          <span className="inline-flex items-center gap-1.5 text-sm">
                            <span
                              aria-hidden
                              className="size-2 rounded-full bg-[color:var(--color-primary)]"
                            />
                            Conectado
                          </span>
                        ) : (
                          <span className="text-sm text-muted-foreground">
                            Sin conectar
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {client.agent_version !== null ? (
                          <span className="font-mono text-xs">
                            v{client.agent_version}
                            {client.agent_seed_template
                              ? ` · ${client.agent_seed_template}`
                              : ""}
                          </span>
                        ) : (
                          <span className="text-sm text-muted-foreground">
                            Sin agente
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {client.broadcasts}
                      </TableCell>
                      <TableCell className="text-right tabular-nums hidden md:table-cell">
                        {client.broadcast_recipients}
                      </TableCell>
                      <TableCell className="text-right tabular-nums hidden md:table-cell">
                        {client.messages_inbound}/{client.messages_outbound}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        ${client.cost_usd.toFixed(4)}
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
