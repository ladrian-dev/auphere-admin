import Link from "next/link";

import { Card, EmptyState } from "@nexus/ui";

import type { ClientSummary } from "@/lib/backend";

export type PickerCopy = {
  title: string;
  lead: string;
  empty: { title: string; body: string; action: string };
};

/**
 * Elegir cliente, la primera pantalla de Rutinas (spec 082, requisito 1.2).
 *
 * Una rutina es de un agente y un agente es de un cliente, así que aquí no hay
 * una lista de todo junto: se elige uno y a partir de ahí se ven las suyas.
 *
 * **Sin clientes no hay nada que elegir**, y eso se dice con todas las letras
 * en vez de enseñar una rejilla vacía: a quien acaba de entrar, una pantalla en
 * blanco le parece un error del producto, no una cuenta recién empezada. La
 * salida es ir a crear el primero (constitución §V: la ausencia se diseña).
 */
export function ClientPicker({ clients, copy }: { clients: ClientSummary[]; copy: PickerCopy }) {
  if (clients.length === 0) {
    return (
      <EmptyState
        title={copy.empty.title}
        description={copy.empty.body}
        action={
          <Link href="/clients" className="rounded-md border px-3 py-2 text-sm font-medium">
            {copy.empty.action}
          </Link>
        }
      />
    );
  }

  return (
    <section aria-labelledby="pick-clients">
      <h2 id="pick-clients" className="text-base font-semibold">
        {copy.title}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{copy.lead}</p>
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
