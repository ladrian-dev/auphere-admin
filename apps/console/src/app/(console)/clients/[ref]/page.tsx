import { ClientSummary, type Block, type ConnectedItem } from "@/components/clients/summary/client-summary";
import { ClientPanelView } from "@/components/clients/v2/client-panel";
import { PanelError } from "@/components/clients/v2/panel-error";
import { SeedRequested } from "@/components/money/request-balance";
import { backendFor, callFor } from "@/lib/backend";
import { clientRecordsApi } from "@/lib/backend/client-records";
import { moneyApi } from "@/lib/backend/money";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getClientCached, getClientV2Cached, getConsoleVersionCached } from "./data";

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

export default async function ClientOverviewPage({ params, searchParams }: { params: Promise<{ ref: string }>; searchParams?: Promise<{ assign?: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  const api = backendFor(principal);
  // Spec 047 (T067, requisito 14): con la consola nueva, el Panel del cliente
  // sustituye al Resumen y a su checklist.
  if ((await getConsoleVersionCached(principal)) === "v2") {
    const call = callFor(principal);
    // Spec 047 (T159): la bolsa la trae el Panel; el relleno y la moneda, sus
    // propias lecturas. Si fallan, el Panel se pinta igual, sin ellas.
    const [panel, bags, detail] = await Promise.all([
      clientRecordsApi(call)
        .getClientPanel(ref)
        .catch(() => null),
      can(principal.role, "usage:read") ? moneyApi(call).listBags().catch(() => null) : null,
      getClientV2Cached(principal, ref).catch(() => null),
    ]);
    if (!panel) return <PanelError />;
    const bag = bags?.find((b) => b.ref === ref) ?? null;
    const currency = bag?.balance.currency ?? detail?.wallet_currency ?? panel.bag.balance?.currency ?? null;
    return (
      <>
        {bag && !can(principal.role, "usage:write") ? <SeedRequested items={[bag]} /> : null}
        <ClientPanelView
        panel={panel}
        canWrite={can(principal.role, "clients:write")}
        money={currency ? { currency, canSetCap: can(principal.role, "usage:write"), refillUpTo: bag?.refill_up_to ?? null } : undefined}
        openBalance={(await searchParams)?.assign === "1"}
        />
      </>
    );
  }

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
        unlimited: client.unlimited_consumption ?? false,
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
