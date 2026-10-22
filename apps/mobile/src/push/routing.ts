import type { Href } from "expo-router";

/**
 * Where a notice opens (R8.6): its conversation, Consumo, or — spec 044,
 * R14.5 — a reservation (`auphere-customers://reservas/<booking_id>`, 043 §1),
 * opened on Reservas with its sheet, which reads the booking by id. The URL comes from the API
 * (`push_payloads`); anything else opens nothing — a notice never navigates
 * somewhere the app does not know.
 */
export function routeFor(data: unknown): Href | null {
  const url = data && typeof data === "object" && "url" in data ? (data as { url: unknown }).url : null;
  if (typeof url !== "string") return null;
  const inbox = /^auphere-customers:\/\/inbox\/([0-9a-fA-F-]{36})$/.exec(url);
  if (inbox) return `/conversacion/${inbox[1]}` as Href;
  if (url === "auphere-customers://usage") return "/consumo";
  const reservation = /^auphere-customers:\/\/reservas\/([A-Za-z0-9_-]{1,64})$/.exec(url);
  if (reservation) return `/reservas?open=${reservation[1]}` as Href;
  return null;
}

const CONVERSATION = "/conversacion/";

/** The conversation a notice is about, if any. */
export function conversationOf(data: unknown): string | null {
  const route = routeFor(data);
  return typeof route === "string" && route.startsWith(CONVERSATION) ? route.slice(CONVERSATION.length) : null;
}
