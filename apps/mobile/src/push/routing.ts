import type { Href } from "expo-router";

/**
 * Where a notice opens (R8.6): its conversation, Consumo, or — spec 044,
 * R14.5 — a reservation (`auphere-customers://reservas/<booking_id>`, 043 §1),
 * opened on Reservas with its sheet, which reads the booking by id.
 *
 * Spec 047 (T170, `events.md` §3.1): the phone's kind `agents.state` carries
 * an agent's cap, its pauses and its numbers' pauses and problems. Spec 056
 * (2.6, 2.7): Agentes is no longer in the app, so it travels with
 * `auphere-customers://home` → Inicio; one delivered before, with
 * `auphere-customers://agents/<agent_id>` (and `/channels/<channel_id>` after
 * it for a number), opens Inicio too. The bag's three (`client.wallet.*`)
 * travel as `client.balance`, to `auphere-customers://usage` → Consumo.
 *
 * The URL comes from the API (`push_payloads`); anything else opens nothing —
 * a notice never navigates somewhere the app does not know.
 */
const UUID = "[0-9a-fA-F-]{36}";
const INBOX = new RegExp(`^auphere-customers://inbox/(${UUID})$`);
const RESERVATION = /^auphere-customers:\/\/reservas\/([A-Za-z0-9_-]{1,64})$/;
/** Spec 047's link to an agent, in notices sent before spec 056: recognised, and it opens Inicio. */
const OLD_AGENT = new RegExp(`^auphere-customers://agents/${UUID}(?:/channels/${UUID})?$`);

export function routeFor(data: unknown): Href | null {
  const url = data && typeof data === "object" && "url" in data ? (data as { url: unknown }).url : null;
  if (typeof url !== "string") return null;
  const inbox = INBOX.exec(url);
  if (inbox) return `/conversacion/${inbox[1]}` as Href;
  if (url === "auphere-customers://usage") return "/consumo";
  const reservation = RESERVATION.exec(url);
  if (reservation) return `/reservas?open=${reservation[1]}` as Href;
  if (url === "auphere-customers://home" || OLD_AGENT.test(url)) return "/";
  return null;
}

const CONVERSATION = "/conversacion/";

/** The conversation a notice is about, if any. */
export function conversationOf(data: unknown): string | null {
  const route = routeFor(data);
  return typeof route === "string" && route.startsWith(CONVERSATION) ? route.slice(CONVERSATION.length) : null;
}
