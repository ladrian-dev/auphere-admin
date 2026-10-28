"use client";

import { Bot, ChevronRight } from "lucide-react";
import Link from "next/link";

import { Callout, EmptyState, StatusBadge } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { ClientAgent } from "@/lib/backend";

import { cardHref, isDefault, visibleText, visibleTone } from "./life-model";

/**
 * La pestaña Agentes de un cliente con la consola nueva (spec 047, historias 7
 * y 19; requisitos 17.2 y 26.1): una tarjeta por agente con su nombre, su estado
 * visible (el mismo texto y tono que en toda la consola, 25.5), si es el agente
 * por defecto y cuántos canales atiende. Lleva a la pestaña que le toca: un
 * borrador, a construir; «Listo · sin canal», a los canales; el resto, al
 * agente. Un borrador abandonado sigue aquí, como «Borrador».
 *
 * «Nuevo agente» solo para quien puede escribir (§V): a quien lee no se le
 * enseña un botón que no podría usar.
 */
export function AgentCards({ refId, agents, canWrite }: { refId: string; agents: ClientAgent[] | null; canWrite: boolean }) {
  const t = useT();
  const listed = agents ? [...agents].sort((a, b) => Number(a.status === "archived") - Number(b.status === "archived")) : [];
  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-cards">
      {/* Sin título ni «Nuevo agente» propios: como el prototipo, la pestaña es
          la lista, y el botón primario está una sola vez, en la cabecera del
          cliente (Andrés, 2026-10-28). */}
      {agents === null ? (
        <Callout tone="danger">{t("builder.agents.error")}</Callout>
      ) : !listed.length ? (
        <EmptyState
          icon={Bot}
          title={t("builder.agents.empty.title")}
          description={canWrite ? t("builder.agents.empty.body") : t("builder.agents.empty.readonly")}
          readonly={!canWrite}
        />
      ) : (
        <ul aria-label={t("builder.agents.list")} className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {listed.map((agent) => (
            <li key={agent.id} className="min-w-0">
              <AgentCard refId={refId} agent={agent} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AgentCard({ refId, agent }: { refId: string; agent: ClientAgent }) {
  const t = useT();
  const channels = agent.channels.length;
  const archived = agent.status === "archived";
  const state = agent.visible_state ?? null;
  return (
    <Link
      href={cardHref(refId, agent)}
      className="group flex h-full min-w-0 items-start gap-3 rounded-md border border-border bg-card p-4 outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"
      data-slot="agent-card"
      data-opens={agent.opens ?? undefined}
    >
      <span className="grid min-w-0 flex-1 gap-2">
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="min-w-0 font-medium break-words">{agent.name}</span>
          {isDefault(agent) && !archived ? <span className="text-xs text-muted-foreground">{t("builder.agents.principal")}</span> : null}
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          {state ? (
            // Spec 047 (25.5): el estado visible de la API, con el mismo texto y tono que en toda la consola.
            <StatusBadge tone={visibleTone(state)}>{visibleText(t, state)}</StatusBadge>
          ) : archived ? (
            <StatusBadge tone="muted">{t("builder.agents.state.archived")}</StatusBadge>
          ) : agent.active_version !== null ? (
            <StatusBadge tone="positive">{t("builder.agents.state.published")}</StatusBadge>
          ) : (
            <StatusBadge tone="muted">{t("builder.agents.state.draft")}</StatusBadge>
          )}
          {!archived && agent.active_version !== null && agent.draft_version !== null ? (
            <span className="text-xs text-muted-foreground">{t("builder.agents.pendingChanges")}</span>
          ) : null}
        </span>
        <span className="text-sm text-muted-foreground">
          {channels === 0
            ? t("builder.agents.channels.none")
            : channels === 1
              ? t("builder.agents.channels.one")
              : t("builder.agents.channels.other", { n: channels })}
        </span>
      </span>
      <ChevronRight aria-hidden="true" className="mt-1 size-4 shrink-0 text-muted-foreground group-hover:text-foreground" />
    </Link>
  );
}
