import Link from "next/link";

import { Card } from "@nexus/ui";

import type { ClientSummary } from "@/lib/backend";

/**
 * Elegir cliente, la primera pantalla de Rutinas (spec 082, requisito 1.2).
 *
 * Una rutina es de un agente y un agente es de un cliente, así que aquí no hay
 * una lista de todo junto: se elige uno y a partir de ahí se ven las suyas.
 */
export function ClientPicker({
  clients,
  title,
  lead,
}: {
  clients: ClientSummary[];
  title: string;
  lead: string;
}) {
  return (
    <section aria-labelledby="pick-clients">
      <h2 id="pick-clients" className="text-base font-semibold">
        {title}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{lead}</p>
      <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {clients.map((client) => (
          <li key={client.external_client_ref}>
            <Card className="p-4">
              <Link
                href={`/schedules?client=${encodeURIComponent(client.external_client_ref)}`}
                className="flex flex-col gap-1"
              >
                <span className="font-medium">{client.name}</span>
                <span className="text-sm text-muted-foreground">{client.timezone}</span>
              </Link>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}
