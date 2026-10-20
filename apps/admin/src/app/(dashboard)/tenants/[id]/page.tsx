import { Check, CircleAlert } from "lucide-react";
import Link from "next/link";

import { Callout, DescriptionList, Section, StatusDot } from "@nexus/ui";

import { backend, type ConversationOut } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";
import { qaApi, type QAThread } from "@/lib/qa-api";
import { requireOperator } from "@/lib/session";

import { readinessChecks } from "./readiness";

const CONVERSATION_TONE = { open: "info", escalated: "danger", closed: "muted" } as const;
const CONVERSATION_LABEL = { open: "Abierta", escalated: "Escalada", closed: "Resuelta" } as const;

/**
 * Spec 036: the client's summary, in two columns on a wide screen (F-pattern):
 * on the left what needs doing and what is happening, on the right the data
 * you look up. What is pending goes first; with nothing pending the checklist
 * folds to one line (progressive disclosure).
 */
export default async function TenantOverview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const operator = await requireOperator();
  const [tenant, health, conversations, connectors, threads] = await Promise.all([
    backend.getTenant(id),
    backend.getTenantHealth(id).catch(() => null),
    backend.listConversations(id, undefined, 6).catch(() => null),
    backend.listTenantConnectors(id).catch(() => null),
    qaApi.listThreads({ operatorId: operator.id, tenantId: id, limit: 3 }).catch(() => [] as QAThread[]),
  ]);
  if (!tenant) return null;
  const partner = tenant.partner_id ? await backend.getPartner(tenant.partner_id).catch(() => null) : null;

  const base = `/tenants/${id}`;
  const broken = connectors?.filter((c) => c.status === "needs_reauth" || c.status === "error") ?? [];
  const checks = readinessChecks({ base, tenant, health, brokenConnectors: broken.map((c) => c.connector_display_name) });
  const pending = checks.filter((c) => !c.ok);
  const done = checks.filter((c) => c.ok);

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <div className="flex min-w-0 flex-col gap-6 xl:col-span-2">
        {pending.length === 0 ? (
          <Callout tone="positive" title="Listo para operar">
            Agente publicado, canal activo, teléfono del dueño y conectores en orden.
          </Callout>
        ) : (
          <Section
            title="Qué falta para operar"
            description={`${done.length} de ${checks.length} pasos hechos.`}
            padded={false}
          >
            <ul className="divide-y divide-border">
              {pending.map((c) => (
                <li key={c.key} className="flex items-start gap-3 px-6 py-3">
                  <CircleAlert className="mt-1 size-4 shrink-0 text-status-warning-text" aria-hidden="true" />
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="text-sm font-medium">{c.label}</span>
                    <span className="text-sm text-pretty text-muted-foreground">{c.detail}</span>
                  </div>
                  {c.href && c.action ? (
                    <Link href={c.href} className="shrink-0 text-sm font-medium text-primary-deep underline-offset-4 hover:underline">
                      {c.action}
                    </Link>
                  ) : null}
                </li>
              ))}
            </ul>
            {done.length > 0 ? (
              <details className="group border-t border-border px-6 py-3">
                <summary className="cursor-pointer text-sm text-muted-foreground select-none hover:text-foreground">
                  Ya está hecho ({done.length})
                </summary>
                <ul className="mt-3 flex flex-col gap-2">
                  {done.map((c) => (
                    <li key={c.key} className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Check className="size-4 shrink-0 text-status-positive-text" aria-hidden="true" />
                      {c.label}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </Section>
        )}

        <Section
          title="Conversaciones recientes"
          actions={
            <Link href={`${base}/conversations`} className="text-sm text-primary-deep underline-offset-4 hover:underline">
              Ver todas
            </Link>
          }
          padded={false}
        >
          {conversations === null ? (
            <p className="px-6 py-4 text-sm text-muted-foreground">No se pudieron leer las conversaciones.</p>
          ) : conversations.items.length === 0 ? (
            <p className="px-6 py-4 text-sm text-muted-foreground">
              Todavía nadie ha escrito. Cuando llegue el primer mensaje aparecerá aquí.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {conversations.items.map((c) => (
                <ConversationRow key={c.id} base={base} conversation={c} />
              ))}
            </ul>
          )}
        </Section>
      </div>

      <aside className="flex min-w-0 flex-col gap-6">
        <Section title="Datos del cliente" description="Se editan desde Acciones.">
          <DescriptionList
            layout="inline"
            items={[
              { key: "slug", term: "Identificador", detail: tenant.slug, mono: true, truncate: true },
              {
                key: "partner",
                term: "Partner",
                detail: partner ? (
                  <Link href={`/partners/${partner.id}`} className="underline-offset-4 hover:underline">
                    {partner.name}
                  </Link>
                ) : (
                  "Auphere directo"
                ),
              },
              { key: "email", term: "Correo", detail: tenant.owner_email ?? "—", truncate: true },
              { key: "phone", term: "Teléfono", detail: tenant.owner_phone ?? "—", mono: true },
              { key: "market", term: "Mercado", detail: tenant.market ?? "—" },
              { key: "tz", term: "Zona horaria", detail: tenant.timezone },
              { key: "created", term: "Alta", detail: fullDateTime(tenant.created_at) },
            ]}
          />
        </Section>
        <Section
          title="Pruebas del agente"
          actions={
            <Link href={`${base}/playground`} className="text-sm text-primary-deep underline-offset-4 hover:underline">
              Abrir
            </Link>
          }
        >
          {threads.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nadie lo ha probado todavía. «Probar agente» abre una conversación de prueba: nada sale de verdad.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {threads.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-3">
                  <Link href={`${base}/playground?thread=${t.id}`} className="truncate text-sm underline-offset-4 hover:underline">
                    {t.title}
                  </Link>
                  <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(t.updated_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </aside>
    </div>
  );
}

function ConversationRow({ base, conversation: c }: { base: string; conversation: ConversationOut }) {
  const who = c.customer_name || c.customer_identifier || "Contacto sin número";
  return (
    <li>
      <Link
        href={`${base}/conversations/${c.id}`}
        className="flex items-center gap-3 px-6 py-3 outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <StatusDot tone={CONVERSATION_TONE[c.status]} label={CONVERSATION_LABEL[c.status]} />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-sm font-medium">{who}</span>
          <span className="truncate text-xs text-muted-foreground">
            {CONVERSATION_LABEL[c.status]} · {c.agent_active ? "Responde el agente" : "La atiende una persona"}
          </span>
        </span>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {relativeTime(c.last_message_at ?? c.updated_at)}
        </span>
      </Link>
    </li>
  );
}
