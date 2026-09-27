import { ClientSummary, type Block, type ConnectedItem } from "@/components/clients/summary/client-summary";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { getClientCached } from "./data";

/**
 * El Resumen del cliente (spec 018, R1).
 *
 * **Cuatro lecturas, en paralelo, cada una con su propio fallo.** No hay un
 * endpoint que las junte, y es a propósito: juntarlas habría hecho que un
 * fallo en cualquiera de las cuatro fuentes tumbara la pantalla entera, que
 * es lo contrario de lo que pide R1.6. Pidiéndolas por separado, el
 * aislamiento de fallos sale gratis en vez de haber que programarlo.
 *
 * Son cuatro **por ficha**, no por fila ni por cliente del partner: la lista
 * de clientes no las hace (R1.8).
 */

/** Una lectura que puede fallar sin arrastrar a las demás. */
async function block<T>(p: Promise<T>): Promise<Block<T>> {
  try {
    return { ok: true, data: await p };
  } catch {
    return { ok: false };
  }
}

export default async function ClientOverviewPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  const api = backendFor(principal);

  const [client, usage, conversations, channels, connectors] = await Promise.all([
    getClientCached(principal, ref),
    can(principal.role, "usage:read") ? block(api.usageV2({ client: ref, days: 30 })) : null,
    can(principal.role, "conversations:read") ? block(api.conversationStats(ref, 30)) : null,
    can(principal.role, "channels:read") ? block(api.listChannels(ref)) : null,
    can(principal.role, "agents:read") ? block(api.listConnectors(ref)) : null,
  ]);

  // Lo que necesita atención primero: es lo único que el partner tiene que
  // hacer con esta lista, y buscarlo entre lo que funciona es trabajo suyo.
  const items: ConnectedItem[] = [];
  let notConnected = 0;
  if (channels?.ok) {
    for (const ch of channels.data.filter((c) => c.status === "active")) {
      // El número lo trae la salud del cliente, no la fila del canal.
      items.push({
        key: `ch-${ch.id}`,
        name: ch.provider,
        status: "connected",
        detail: client.health.display_phone_number ?? ch.provider_identifier,
      });
    }
  }
  if (connectors?.ok) {
    for (const c of connectors.data) {
      if (!c.installed && !c.status) {
        notConnected += 1;
        continue;
      }
      items.push({
        key: c.slug,
        name: c.display_name,
        status: c.status ?? "none",
        unlocks: c.tools_total || null,
      });
    }
  }
  items.sort((a, b) => Number(connectedOk(a.status)) - Number(connectedOk(b.status)));

  return (
    <ClientSummary
      refId={ref}
      role={principal.role}
      client={{
        name: client.name,
        timezone: client.timezone,
        status: client.status,
        sector: client.sector ?? null,
        health: client.health,
        quota: client.quota ?? null,
      }}
      usage={
        usage === null || !usage.ok
          ? { ok: false }
          : {
              ok: true,
              data: {
                units: usage.data.month.units,
                projected: usage.data.month.projected_month_units,
                basisDays: usage.data.month.basis_days,
                daysInMonth: usage.data.month.days_in_month,
              },
            }
      }
      conversations={conversations}
      connected={channels === null && connectors === null ? { ok: false } : { ok: true, data: items }}
      notConnected={notConnected}
    />
  );
}

function connectedOk(status: string): boolean {
  return status === "connected" || status === "active";
}
