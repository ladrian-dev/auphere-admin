import { notFound, redirect } from "next/navigation";

import { AgentBuilder } from "@/components/builder/agent-builder";
import { sectionForTab } from "@/components/builder/builder-model";
import { missingFrom } from "@/components/builder/missing-model";
import { channelHref } from "@/components/builder/channel-model";
import { ArchivedAgent } from "@/components/builder/archived-agent";
import { metaSignupConfig } from "@/components/channels/connect-choice";
import { clientHref } from "@/components/shell/routes-v2";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor, callFor } from "@/lib/backend";
import { businessSectionsApi } from "@/lib/backend/business-sections";
import type { ChannelPage } from "@/lib/backend/channel-config-types";
import { env } from "@/lib/env";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getClientV2Cached, getConsoleVersionCached } from "../../data";

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
 * Spec 047 (historia 21): Conectores (el catálogo del agente, conectar y el
 * permiso de cada uno; `?tab=integrations`). Avanzado dice que el modelo lo
 * gestiona Auphere (64.1; D55); `?tab=quality` llega a esa línea.
 *
 * Spec 047 (historias 10, 11 y 22): con `knowledge:read`, la sección
 * Conocimiento (sus fuentes y «Enseñar»); con `channels:read`, la sección
 * Canales (sus números, el ⋯ de cada uno con lo que permite su página y el
 * enlace del dueño). Lo que no se puede leer se dice en su sección.
 *
 * Como el prototipo aprobado, «Qué sabe» resume la ficha del negocio («5
 * servicios · 1 sede · horario (de la ficha)»): se leen sus servicios, sedes y
 * horario. Si alguna no llega, la fila dice solo lo del agente.
 *
 * «Nuevo agente» termina aquí (prototipo §3.3): con `?job=` se lee su trabajo
 * y, si es de este agente y dejó preguntas, salen encima de la tabla para
 * responderlas una a una. Si el trabajo no se puede leer, la pantalla sigue sin ellas.
 *
 * Spec 047, enmienda del 2026-10-30 (T228; 65.3 y 65.4): «No tenemos
 * herramienta para: …» sale del `missing_capabilities` del borrador, que la API
 * manda siempre. Un borrador de antes sin el campo cae en el del trabajo de
 * «Nuevo agente» (`?job=`), que recién creado dice lo mismo.
 *
 * Spec 047 (63.1; hueco H5): con `?canal=` la pestaña Canales abre la
 * configuración de ese número dentro del agente (su página, su historial y
 * cómo se asigna o se pide saldo desde sus comprobaciones). Si el número es de
 * otro agente, se va al suyo; si no se puede leer, se ve la lista.
 */
export default async function AgentScreenPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string; agentId: string }>;
  searchParams?: Promise<{ tab?: string; job?: string; canal?: string }>;
}) {
  const { ref, agentId } = await params;
  const query = (await searchParams) ?? {};
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
  const biz = businessSectionsApi(callFor(principal));
  // Spec 047 (63.1): el canal que se configura dentro del agente.
  const canal = readsChannels && typeof query.canal === "string" && UUID_RE.test(query.canal) ? query.canal : null;
  const [draft, proposals, tests, preview, history, sessions, agents, knowledge, channels, performance, conversations, improvements, client, bizServices, bizLocations, bizHours, canalPage, canalHistory] = await Promise.all([
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
    // El nombre del cliente bajo el título («de Flor y Encanto»): la misma lectura que el layout.
    getClientV2Cached(principal, ref).catch(() => null),
    run(() => biz.getServices(ref)),
    run(() => biz.getLocations(ref)),
    run(() => biz.getHours(ref)),
    canal ? run(() => api.getChannelPage(ref, canal)) : null,
    canal ? run(() => api.getChannelHistory(ref, canal)) : null,
  ]);
  // Pasó a otro agente: su configuración se abre en el suyo.
  if (canal && canalPage?.ok && canalPage.data.agent && canalPage.data.agent.id !== agentId) redirect(channelHref(ref, canalPage.data.agent.id, canal));
  // Las preguntas que dejó el borrador de «Nuevo agente», si el trabajo es de este agente.
  const job = typeof query.job === "string" && UUID_RE.test(query.job) && can(principal.role, "agents:write") ? await run(() => api.getDraftJob(query.job!)) : null;
  const ownJob = job?.ok && job.data.kind === "agent_draft" && job.data.status === "done" && (job.data.result?.agent_id ?? job.data.agent_id) === agentId ? job.data : null;
  const questions = ownJob?.result?.questions.length
    ? { job: ownJob.job_id, questions: ownJob.result.questions.slice(0, 5), discarded: ownJob.result.discarded ?? { count: 0, reasons: [] } }
    : null;
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
  const business =
    bizServices.ok && bizLocations.ok && bizHours.ok
      ? {
          services: bizServices.data.items.filter((x) => !x.archived).length,
          locations: bizLocations.data.items.filter((x) => !x.archived).length,
          hours: bizHours.data.label != null || Object.values(bizHours.data.days).some((shifts) => shifts.length > 0),
        }
      : null;
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
  // Spec 047 (45.1): «Asignar saldo» se abre en el sitio si esta persona puede; si no, «Pedir saldo» (45.7).
  const allowed = client?.allowed ?? [];
  const channelConfig =
    canal && canalPage?.ok
      ? {
          page: canalPage.data,
          history: canalHistory?.ok ? canalHistory.data : null,
          canWrite: can(principal.role, "channels:write"),
          balance: client
            ? allowed.includes("assign_balance")
              ? { name: client.name, mode: "assign" as const }
              : allowed.includes("request_balance")
                ? { name: client.name, mode: "request" as const }
                : null
            : null,
        }
      : null;
  return (
    <AgentBuilder
      key={draft.data.agent_id}
      refId={ref}
      draft={{ ...draft.data, missing_capabilities: missingFrom(draft.data.missing_capabilities, ownJob?.result?.missing_capabilities) }}
      proposals={ok(proposals)}
      canWrite={can(principal.role, "agents:write")}
      quality={{ tests: ok(tests), preview: ok(preview), history: ok(history), sessions: ok(sessions) }}
      header={ok(header)}
      agents={ok(agents) ?? []}
      knowledge={knowledge ? { data: ok(knowledge), canWrite: can(principal.role, "knowledge:write") } : undefined}
      channels={
        channels
          ? {
              data: ok(channels),
              pages,
              canWrite: can(principal.role, "channels:write"),
              fromPhone: env().NEXUS_OWNER_LINK_FROM_PHONE,
              // «Conectar WhatsApp» desde la pestaña Canales: el mismo alta de Meta que la página de canales del cliente.
              meta: metaSignupConfig(env()),
            }
          : undefined
      }
      advanced={advanced}
      performance={{ performance: ok(performance), conversations: conversations ? ok(conversations) : undefined }}
      improvements={{ data: ok(improvements) }}
      // Spec 047 (historia 21): los Conectores se leen al montar su sección: el
      // catálogo pregunta al proveedor y no frena el resto de la pantalla.
      // Avanzado ya no lee la calidad (64.1; D55): el modelo lo gestiona Auphere.
      connectors={{ canWrite: can(principal.role, "agents:write") }}
      channelConfig={channelConfig}
      // T218: se pidió un canal que no se pudo leer (404, de otro cliente o la API no respondió): la pestaña Canales lo dice.
      channelUnavailable={Boolean(canal && canalPage && !canalPage.ok)}
      initialSection={sectionForTab(query.tab)}
      questions={questions}
      clientName={client?.name ?? null}
      business={business}
    />
  );
}
