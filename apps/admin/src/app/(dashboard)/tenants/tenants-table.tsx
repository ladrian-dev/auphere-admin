"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  EmptyState,
  Input,
  NativeSelect,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from "@nexus/ui";

import { ChannelLogo } from "@/components/brand/channel-logo";
import { TenantActionsMenu } from "@/components/tenants/tenant-actions-menu";
import { compareRows, inView, isQuiet, reasonsFor, SORTS, VIEWS, type Sort, type View } from "@/components/tenants/health";
import type { Tenant, TenantHealth } from "@/lib/backend";
import { planLabel, relativeTime, statusLabel } from "@/lib/format";
import { filterRows } from "@/lib/list-filter";

const STATUS_TONE: Record<string, "positive" | "warning" | "muted"> = {
  active: "positive",
  paused: "warning",
  archived: "muted",
  provisioning: "warning",
};

/** The partner facet's value for a client that belongs to no partner. */
export const DIRECT = "__direct__";

type Props = {
  tenants: Tenant[];
  health: TenantHealth[];
  partners: { id: string; name: string }[];
  paidThisMonth: string[];
  monthName: string;
};

const VIEW_KEYS = new Set(VIEWS.map((v) => v.key));
const SORT_KEYS = new Set(SORTS.map((s) => s.key));

/**
 * Spec 036: the client list. Views as tabs with counts (Hick: one glance, not
 * three drop-downs), what needs attention first and in words (Von Restorff,
 * serial position), the whole row opens the client (Fitts), and every choice
 * lives in the address so coming back finds the list as it was (H3).
 */
export function TenantsTable({ tenants, health, partners, paidThisMonth, monthName }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view = (VIEW_KEYS.has(params.get("view") as View) ? params.get("view") : "all") as View;
  const sort = (SORT_KEYS.has(params.get("sort") as Sort) ? params.get("sort") : "attention") as Sort;
  const partner = params.get("partner") ?? "";
  const plan = params.get("plan") ?? "";
  const [q, setQ] = useState(params.get("q") ?? "");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  // Typing filters at once (Doherty); the address catches up without
  // stacking history, so «atrás» never undoes a letter.
  useEffect(() => {
    const id = setTimeout(() => {
      const next = new URLSearchParams(window.location.search);
      if (q.trim()) next.set("q", q.trim());
      else next.delete("q");
      const qs = next.toString();
      window.history.replaceState(null, "", qs ? `${pathname}?${qs}` : pathname);
    }, 250);
    return () => clearTimeout(id);
  }, [q, pathname]);

  const paid = useMemo(() => new Set(paidThisMonth), [paidThisMonth]);
  const partnerName = useMemo(() => new Map(partners.map((p) => [p.id, p.name])), [partners]);
  const healthOf = useMemo(() => new Map(health.map((h) => [h.tenant_id, h])), [health]);
  const showBilling = tenants.some((t) => t.billing_plan_id);
  const plans = useMemo(() => [...new Set(tenants.map((t) => t.plan))], [tenants]);

  const all = useMemo(
    () => tenants.map((t) => ({ tenant: t, health: healthOf.get(t.id), reasons: reasonsFor(t, healthOf.get(t.id)) })),
    [tenants, healthOf],
  );
  const faceted = useMemo(
    () =>
      filterRows(
        all,
        q,
        (r) => [
          r.tenant.name,
          r.tenant.slug,
          r.tenant.owner_email,
          r.tenant.owner_phone,
          r.health?.primary_channel?.identifier,
          r.tenant.partner_id ? partnerName.get(r.tenant.partner_id) : "Auphere directo",
        ],
        [
          { value: partner, of: (r) => r.tenant.partner_id ?? DIRECT },
          { value: plan, of: (r) => r.tenant.plan },
        ],
      ),
    [all, q, partner, plan, partnerName],
  );
  const counts = useMemo(
    () => Object.fromEntries(VIEWS.map((v) => [v.key, faceted.filter((r) => inView(v.key, r.tenant, r.reasons)).length])),
    [faceted],
  ) as Record<View, number>;
  const rows = useMemo(
    () => faceted.filter((r) => inView(view, r.tenant, r.reasons)).sort(compareRows(sort)),
    [faceted, view, sort],
  );
  const filtered = Boolean(q.trim() || partner || plan);

  return (
    <div className="flex flex-col gap-4">
      <nav aria-label="Vistas de clientes" className="flex gap-1 overflow-x-auto border-b border-border">
        {VIEWS.map((v) => {
          const current = v.key === view;
          return (
            <button
              key={v.key}
              type="button"
              aria-pressed={current}
              onClick={() => setParam("view", v.key === "all" ? "" : v.key)}
              className={cn(
                "-mb-px inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                current ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {v.label}
              <span
                className={cn(
                  "rounded-full px-2 text-xs tabular-nums",
                  v.key === "attention" && counts.attention > 0
                    ? "bg-status-warning-bg text-status-warning-text"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {counts[v.key]}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="flex flex-col gap-2 md:flex-row md:items-center">
        <Input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por nombre, número o correo"
          aria-label="Buscar clientes"
          className="md:max-w-sm"
        />
        <NativeSelect value={partner} onChange={(e) => setParam("partner", e.target.value)} aria-label="Partner" wrapperClassName="md:w-56">
          <option value="">Cualquier partner</option>
          <option value={DIRECT}>Auphere directo</option>
          {partners.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </NativeSelect>
        {plans.length > 1 ? (
          <NativeSelect value={plan} onChange={(e) => setParam("plan", e.target.value)} aria-label="Plan" wrapperClassName="md:w-44">
            <option value="">Cualquier plan</option>
            {plans.map((p) => (
              <option key={p} value={p}>
                {planLabel(p)}
              </option>
            ))}
          </NativeSelect>
        ) : null}
        {filtered ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQ("");
              const next = new URLSearchParams(params.toString());
              for (const k of ["q", "partner", "plan"]) next.delete(k);
              const qs = next.toString();
              router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
            }}
          >
            Quitar filtros
          </Button>
        ) : null}
        <NativeSelect
          value={sort}
          onChange={(e) => setParam("sort", e.target.value === "attention" ? "" : e.target.value)}
          aria-label="Ordenar"
          wrapperClassName="md:ml-auto md:w-52"
        >
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </NativeSelect>
      </div>

      <p className="sr-only" aria-live="polite">
        {rows.length} clientes en esta vista
      </p>

      {rows.length === 0 ? (
        <EmptyState
          title={view === "attention" && !filtered ? "Ningún cliente necesita nada" : "Ningún cliente coincide"}
          description={
            view === "attention" && !filtered ? "Todos atienden con normalidad." : "Prueba con otro nombre o quita algún filtro."
          }
          readonly
        />
      ) : (
        <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cliente</TableHead>
                <TableHead className="hidden md:table-cell">Canal</TableHead>
                <TableHead className="hidden lg:table-cell">Agente</TableHead>
                <TableHead className="hidden sm:table-cell">Actividad</TableHead>
                <TableHead>Estado</TableHead>
                {showBilling ? <TableHead className="hidden xl:table-cell">Mensualidad de {monthName}</TableHead> : null}
                <TableHead className="w-12">
                  <span className="sr-only">Acciones</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(({ tenant: t, health: h, reasons }) => (
                <TableRow key={t.id} className="relative cursor-pointer hover:bg-muted/50">
                  <TableCell>
                    <div className="flex min-w-0 flex-col gap-1">
                      {/* The name's link stretches over the row: one big target (Fitts). */}
                      <Link
                        href={`/tenants/${t.id}`}
                        className="truncate font-medium outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline"
                      >
                        {t.name || "Sin nombre"}
                      </Link>
                      <span className="truncate text-xs text-muted-foreground">
                        {t.partner_id ? partnerName.get(t.partner_id) ?? "Partner" : "Auphere directo"}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    {h?.primary_channel ? (
                      <span className="inline-flex items-center gap-2">
                        <ChannelLogo channel={h.primary_channel.type} size="sm" />
                        <span
                          className={cn(
                            "font-mono text-xs",
                            h.primary_channel.status !== "active" && "text-status-danger-text",
                          )}
                        >
                          {h.primary_channel.identifier}
                        </span>
                        {h.channels_active > 1 ? (
                          <span className="text-xs text-muted-foreground">+{h.channels_active - 1}</span>
                        ) : null}
                      </span>
                    ) : (
                      <span className="text-sm text-muted-foreground">Sin canal</span>
                    )}
                  </TableCell>
                  <TableCell className="hidden text-sm lg:table-cell">
                    {h ? (
                      h.agent_version !== null ? (
                        `Versión ${h.agent_version}`
                      ) : (
                        <span className="text-muted-foreground">Sin publicar</span>
                      )
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="hidden text-sm sm:table-cell">
                    {h?.last_message_at ? (
                      <span className="flex flex-col gap-1">
                        <span
                          className={cn("tabular-nums", isQuiet(h) && "text-status-warning-text")}
                          title={isQuiet(h) ? "Nadie escribe desde hace más de dos semanas" : undefined}
                        >
                          {relativeTime(h.last_message_at)}
                        </span>
                        {h.open_conversations > 0 ? (
                          <span className="text-xs text-muted-foreground tabular-nums">
                            {h.open_conversations} {h.open_conversations === 1 ? "abierta" : "abiertas"}
                          </span>
                        ) : null}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Sin mensajes</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {reasons.length > 0 ? (
                      <span
                        className={cn(
                          "inline-flex items-center gap-2 text-sm",
                          reasons[0]!.tone === "danger" ? "text-status-danger-text" : "text-status-warning-text",
                        )}
                        title={reasons.map((r) => r.label).join(" · ")}
                      >
                        <StatusDot tone={reasons[0]!.tone} />
                        {reasons[0]!.label}
                        {reasons.length > 1 ? <span className="text-xs">+{reasons.length - 1}</span> : null}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-2 text-sm">
                        <StatusDot tone={STATUS_TONE[t.status] ?? "muted"} />
                        {statusLabel(t.status)}
                      </span>
                    )}
                  </TableCell>
                  {showBilling ? (
                    <TableCell className="relative hidden xl:table-cell">
                      {paid.has(t.id) ? (
                        <Badge variant="secondary">Pagada</Badge>
                      ) : t.billing_plan_id ? (
                        <Link
                          href={`/tenants/${t.id}/billing`}
                          className="relative z-10 text-sm text-muted-foreground underline-offset-4 hover:underline"
                        >
                          Sin anotar
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  ) : null}
                  <TableCell className="relative z-10 text-right">
                    <TenantActionsMenu tenantId={t.id} slug={t.slug} name={t.name} status={t.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
