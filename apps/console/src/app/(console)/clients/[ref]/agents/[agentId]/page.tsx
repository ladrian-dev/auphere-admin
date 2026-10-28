import { notFound, redirect } from "next/navigation";

import { AgentBuilder } from "@/components/builder/agent-builder";
import { sectionForTab } from "@/components/builder/builder-model";
import { ArchivedAgent } from "@/components/builder/archived-agent";
import { clientHref } from "@/components/shell/routes-v2";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { ChannelPage } from "@/lib/backend/channel-config-types";
import { env } from "@/lib/env";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getConsoleVersionCached } from "../../data";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("builder.agents.title") };
}

/**
 * La pantalla de un agente con la consola nueva (spec 047, historias 7, 8 y 9):
 * su borrador por bloques, cada uno editable en línea, la barra de «Guardar»,
 * el probador, el copiloto, las pruebas, la revisión, el historial y las
 * propuestas. Con la cabecera de su vida: estado, ⋯ (renombrar, pausar,
 * archivar, por defecto) y, archivado, solo «Restaurar» (historias 19 y 20). Con la consola de hoy, el
 * agente se edita en la pestaña «Agente» (`?agent=`).
 *
 * Un agente que no es de este cliente es un 404, no una pantalla vacía. Si las
 * propuestas no se pueden leer, el borrador se pinta igual y lo dice.
 *
 * Spec 047 (historias 31, 32 y 33): Recepción (sus destinos y cuándo derivar),
 * Rendimiento (30 días y las conversaciones con solo metadatos, con
 * `conversations:read`) y Mejoras (las sugerencias de la semana y las
 * correcciones del negocio). `?tab=performance` e `?tab=improvements` llevan a
 * ellas. Cada parte que no llega lo dice en su sección.
 *
 * Spec 047 (historias 21 y 23): Conectores (el catálogo del agente, conectar
 * y el permiso de cada uno; `?tab=integrations`) y Avanzado › Calidad (las
 * opciones con su precio por mensaje y «Comprobar la calidad»;
 * `?tab=quality`).
 *
 * Spec 047 (historias 10, 11 y 22): con `knowledge:read`, la sección
 * Conocimiento (sus fuentes y «Enseñar»); con `channels:read`, la sección
 * Canales (sus números, el ⋯ de cada uno con lo que permite su página y el
 * enlace del dueño). Lo que no se puede leer se dice en su sección.
 */
export default async function AgentScreenPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string; agentId: string }>;
  searchParams?: Promise<{ tab?: string }>;
}) {
  const { ref, agentId } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/agents/${agentId}`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if ((await getConsoleVersionCached(principal)) !== "v2") {
    redirect(`/clients/${encodeURIComponent(ref)}/agent${UUID_RE.test(agentId) ? `?agent=${encodeURIComponent(agentId)}` : ""}`);
  }
  if (!can(principal.role, "agents:read")) redirect(clientHref(ref));
  if (!UUID_RE.test(agentId)) notFound();

  const api = backendFor(principal);
  // Spec 047 (historias 19 y 20): la cabecera con la vida del agente. Un agente
  // archivado no tiene borrador que leer: se ve en solo lectura, con «Restaurar».
  // Si la cabecera no llega, la pantalla sigue sin ella: el borrador dice si existe.
  const header = await run(() => api.getAgentHeader(ref, agentId));
  if (header.ok && header.data.lifecycle === "archived") return <ArchivedAgent key={`${agentId}:archived`} refId={ref} header={header.data} />;

  // La revisión no se lee aquí: crea propuestas al correr, y esta página se
  // vuelve a pintar con cada guardado. La pide la pantalla cuando cambia el borrador.
  const readsKnowledge = can(principal.role, "knowledge:read");
  const readsChannels = can(principal.role, "channels:read");
  // Spec 047 (44.1): Agente › Avanzado, con el tope y lo gastado del mes en la
  // moneda de la bolsa del cliente; vienen con la cabecera del agente.
  const readsMoney = can(principal.role, "usage:read");
  // Spec 047 (historia 31): la lista de conversaciones (solo metadatos) es de quien puede leerlas.
  const readsConversations = can(principal.role, "conversations:read");
  const [draft, proposals, tests, preview, history, sessions, agents, knowledge, channels, performance, conversations, improvements] = await Promise.all([
    run(() => api.getBuilderDraft(ref, agentId)),
    run(() => api.listProposals(ref, agentId)),
    run(() => api.getAgentTests(ref, agentId)),
    run(() => api.getPublishPreview(ref, agentId)),
    run(() => api.getAgentHistory(ref, agentId)),
    run(() => api.listPlaygroundSessions(ref, agentId)),
    run(() => api.listAgents(ref)),
    readsKnowledge ? run(() => api.getAgentKnowledge(ref, agentId)) : null,
    readsChannels ? run(() => api.listAgentChannels(ref, agentId)) : null,
    run(() => api.getAgentPerformance(ref, agentId, 30)),
    readsConversations ? run(() => api.listAgentConversations(ref, agentId)) : null,
    run(() => api.listImprovements(ref, agentId)),
  ]);
  if (!draft.ok) {
    if (draft.status === 404 || draft.status === 422) notFound();
    throw new Error(`agent draft ${draft.status}`);
  }
  const ok = <T,>(res: { ok: true; data: T } | { ok: false }): T | null => (res.ok ? res.data : null);
  // El ⋯ de cada número necesita lo que permite y a quién puede pasar: su página.
  const pages: Record<string, ChannelPage | null> = {};
  if (channels?.ok) {
    const read = await Promise.all(channels.data.channels.map((c) => run(() => api.getChannelPage(ref, c.id))));
    channels.data.channels.forEach((c, i) => (pages[c.id] = ok(read[i]!)));
  }
  const h = header.ok ? header.data : null;
  const currency = h?.cap_currency ?? null;
  const advanced =
    readsMoney && h && currency
      ? {
          cap: h.monthly_cap_micros != null ? { amount_micros: h.monthly_cap_micros, currency } : null,
          spent: { amount_micros: h.month_spent_micros ?? 0, currency },
          currency,
          canWrite: can(principal.role, "usage:write"),
        }
      : undefined;
  return (
    <AgentBuilder
      key={draft.data.agent_id}
      refId={ref}
      draft={draft.data}
      proposals={ok(proposals)}
      canWrite={can(principal.role, "agents:write")}
      quality={{ tests: ok(tests), preview: ok(preview), history: ok(history), sessions: ok(sessions) }}
      header={ok(header)}
      agents={ok(agents) ?? []}
      knowledge={knowledge ? { data: ok(knowledge), canWrite: can(principal.role, "knowledge:write") } : undefined}
      channels={
        channels
          ? { data: ok(channels), pages, canWrite: can(principal.role, "channels:write"), fromPhone: env().NEXUS_OWNER_LINK_FROM_PHONE }
          : undefined
      }
      advanced={advanced}
      performance={{ performance: ok(performance), conversations: conversations ? ok(conversations) : undefined }}
      improvements={{ data: ok(improvements) }}
      // Spec 047 (historias 21 y 23): Conectores y Avanzado › Calidad se leen al
      // montar su sección: el catálogo pregunta al proveedor y la calidad al
      // router, y ninguno de los dos frena el resto de la pantalla.
      connectors={{ canWrite: can(principal.role, "agents:write") }}
      modelQuality={{ canWrite: can(principal.role, "agents:write") }}
      initialSection={sectionForTab((await searchParams)?.tab)}
    />
  );
}
