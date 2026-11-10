import type { MessageKey } from "@/i18n/messages";
import type { ClientAgent } from "@/lib/backend";
import type { AgentHeader, AgentVisibleState, ChannelDestination } from "@/lib/backend/agent-life-types";
import type { BusinessRecord, Suggestion } from "@/lib/backend/client-records";

import { agentHref, clientHref } from "@/components/shell/routes-v2";

import { channelsHref } from "./quality-model";

/**
 * Spec 047 (historias 19 y 20, T124) — la vida de un agente sin pintar nada: el
 * texto y el tono de su estado visible (los de `clients.v2.agent.*`, los mismos
 * en toda la consola, requisito 25.5), la pestaña que abre su tarjeta (26.1) y
 * lo que hace falta para archivarlo (28.1, 28.4).
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const CODES = new Set(["archived", "paused", "draft", "serving", "testing", "ready_no_channel"]);
const REASONS = new Set(["manual", "no_balance", "agent_cap", "client_paused", "client_archived"]);
const TONES = new Set(["positive", "info", "warn", "danger", "muted"]);

/** «Atendiendo», «Pausado · sin saldo»… El texto lo pone la consola, el estado la API. */
export function visibleText(t: T, state: AgentVisibleState): string {
  if (state.code === "paused") {
    const reason = state.reason && REASONS.has(state.reason) ? state.reason : "manual";
    return t("clients.v2.agent.paused", { reason: t(`clients.v2.pause.${reason}` as MessageKey) });
  }
  return CODES.has(state.code) ? t(`clients.v2.agent.${state.code}` as MessageKey) : state.code;
}

export function visibleTone(state: AgentVisibleState): "positive" | "info" | "warn" | "danger" | "muted" {
  return TONES.has(state.tone) ? (state.tone as "positive" | "info" | "warn" | "danger" | "muted") : "muted";
}

/** Adónde lleva la tarjeta: a construir, a los canales o al agente (26.1). */
export function cardHref(refId: string, agent: Pick<ClientAgent, "id" | "opens">): string {
  return agent.opens === "channels" ? channelsHref(refId) : agentHref(refId, agent.id);
}

/** ¿Es el agente por defecto? Sin el campo nuevo, el principal de antes. */
export function isDefault(agent: Pick<ClientAgent, "is_default" | "is_principal">): boolean {
  return agent.is_default ?? agent.is_principal;
}

/** Los otros agentes vivos del cliente: a quién puede ir un número. */
export function otherLiveAgents(agents: readonly ClientAgent[], agentId: string): ClientAgent[] {
  return agents.filter((a) => a.id !== agentId && a.status !== "archived" && a.lifecycle !== "archived");
}

/** El destino elegido de cada número, o `null` si falta alguno (28.1). */
export function destinations(channels: readonly { id: string }[], chosen: Readonly<Record<string, string>>): ChannelDestination[] | null {
  const out: ChannelDestination[] = [];
  for (const ch of channels) {
    const to = chosen[ch.id];
    if (!to) return null;
    out.push({ channel_id: ch.id, to });
  }
  return out;
}

/** Lo que el ⋯ ofrece, en este orden: solo lo permitido (§V). */
export const MENU_ORDER = ["rename", "pause", "resume", "make_default", "archive", "restore"] as const;
export function menuItems(header: Pick<AgentHeader, "allowed">): (typeof MENU_ORDER)[number][] {
  return MENU_ORDER.filter((a) => header.allowed.includes(a));
}

/** «Nuevo agente» de un cliente, en su pestaña Agentes. Sin `"use client"`: lo usa también el servidor. */
export function newAgentHref(refId: string): string {
  return `${clientHref(refId, "agents")}/new`;
}

/** Las sugerencias del constructor que quedan por decidir en la ficha (18.2). */
export function builderSuggestions(record: Pick<BusinessRecord, "suggestions"> | null): Suggestion[] {
  return (record?.suggestions ?? []).filter((s) => s.source === "builder");
}

/** «Crear este agente»: «Nuevo agente» con su nombre y su descripción ya escritos (18.4). */
export function proposedAgentHref(refId: string, agent: { name: string; description: string }): string {
  return `${newAgentHref(refId)}?name=${encodeURIComponent(agent.name)}&description=${encodeURIComponent(agent.description)}`;
}
