import { AlertTriangle, CheckCircle2, Handshake, Inbox, Store, UserPlus, Wallet } from "lucide-react";
import Link from "next/link";

import { ErrorState, Metric, PageHeader } from "@nexus/ui";

import { backend, type AdminOverview } from "@/lib/backend";
import { formatCents, relativeTime } from "@/lib/format";

export const metadata = { title: "Panel" };
export const dynamic = "force-dynamic";

type AttentionRow = { key: string; href: string; title: string; detail: string };

/** R3.2: everything waiting on the team, oldest ticket first. */
function attentionRows(o: AdminOverview): AttentionRow[] {
  return [
    ...o.open_tickets.map((t) => ({
      key: `t-${t.id}`,
      href: `/tickets/${t.id}`,
      title: `Ticket ${t.ticket_ref} · ${t.topic}`,
      detail: `${t.partner_name} · abierto ${relativeTime(t.opened_at)}`,
    })),
    ...o.clients_without_cap.map((c) => ({
      key: `c-${c.tenant_id}`,
      href: `/tenants/${c.tenant_id}`,
      title: `${c.name} se quedó sin tope`,
      detail: `Su agente no responde hasta que ${c.partner_name} le asigne saldo.`,
    })),
    ...o.pending_signups.map((s) => ({
      key: `s-${s.id}`,
      href: "/signups",
      title: `Alta pendiente · ${s.email}`,
      detail: `Solicitada ${relativeTime(s.created_at)}`,
    })),
  ];
}

export default async function HomePage() {
  const overview: AdminOverview | null = await backend.getOverview().catch(() => null);
  if (!overview) {
    return (
      <>
        <PageHeader eyebrow="Auphere" title="Panel" />
        <ErrorState title="No se pudo leer el estado de la plataforma" description="La API no respondió. El resto del panel sigue disponible desde el menú." />
      </>
    );
  }
  const rows = attentionRows(overview);
  const n = (v: number) => v.toLocaleString("es");
  const unread = new Set(overview.unreadable);

  return (
    <>
      <PageHeader eyebrow="Auphere" title="Panel" description="Cómo está la plataforma hoy y qué espera al equipo." />

      <section aria-label="Cifras" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        <Metric
          icon={<Handshake />}
          label="Partners activos"
          value={n(overview.partners.active)}
          hint={`de ${n(overview.partners.total)}`}
          href="/partners"
        />
        <Metric
          icon={<Store />}
          label="Clientes activos"
          value={n(overview.clients.active)}
          hint={overview.clients.paused > 0 ? `${n(overview.clients.paused)} en pausa` : `de ${n(overview.clients.total)}`}
          href="/tenants"
        />
        <Metric
          icon={<Wallet />}
          label="Saldo de los partners"
          value={unread.has("balance") ? "—" : formatCents(overview.balance_cents)}
          hint={unread.has("balance") ? "No se pudo leer el saldo" : "Disponible, suma de todos"}
          href="/partners"
        />
        <Metric
          icon={<Inbox />}
          label="Tickets abiertos"
          value={unread.has("tickets") ? "—" : n(overview.tickets_open)}
          hint={unread.has("tickets") ? "No se pudieron leer" : undefined}
          href="/tickets"
        />
        <Metric icon={<UserPlus />} label="Altas pendientes" value={n(overview.signups_pending)} href="/signups" />
      </section>

      {rows.length === 0 && overview.unreadable.length === 0 ? (
        <div className="flex items-center gap-3 rounded-md bg-card px-4 py-3 ring-1 ring-foreground/10" role="status">
          <CheckCircle2 aria-hidden="true" className="size-5 shrink-0 text-status-positive" />
          <p className="text-sm">Nada espera al equipo: sin tickets abiertos, sin altas pendientes y todos los clientes con tope.</p>
        </div>
      ) : (
        <section aria-labelledby="attention-h" className="flex flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-status-danger/30">
          <h2 id="attention-h" className="flex items-center gap-2 text-base font-semibold">
            <AlertTriangle aria-hidden="true" className="size-4 text-status-danger" />
            Necesita tu atención
            <span className="rounded-full bg-status-danger/15 px-2 text-xs tabular-nums">{n(rows.length)}</span>
          </h2>
          {overview.unreadable.includes("caps") ? (
            <p className="text-sm text-status-warning-text">No se pudieron leer los topes de los clientes: la lista puede estar incompleta.</p>
          ) : null}
          <ul className="divide-y divide-border">
            {rows.map((r) => (
              <li key={r.key}>
                <Link href={r.href} className="flex flex-col gap-1 rounded-sm py-3 outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring">
                  <span className="text-sm font-medium">{r.title}</span>
                  <span className="text-sm text-muted-foreground">{r.detail}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
