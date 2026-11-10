import { describe, expect, it } from "vitest";

import { messages } from "@/i18n/messages";
import type { Notification } from "@/lib/backend/onboarding";

import { hrefFor, TITLE } from "../lite-notifications-bell";

/**
 * Spec 047 (events.md §3.1, 49.6) — la campana de la persona del cliente dice
 * cada aviso que le llega y la lleva a SU consola, solo si tiene ese módulo.
 */
const notice = (kind: string, over: Partial<Notification> = {}): Notification => ({
  id: "n1",
  kind,
  severity: "info",
  data: {},
  external_client_ref: "flor",
  read: false,
  created_at: "2026-10-28T10:00:00Z",
  ...over,
});

describe("la campana de la lite", () => {
  it("tiene palabras para cada aviso que la API manda al cliente", () => {
    const toClient = ["client.wallet.low", "client.wallet.not_enough", "client.wallet.empty", "agent.cap.warning", "agent.cap.reached", "agent.paused", "agent.resumed", "channel.paused", "channel.resumed", "channel.problem"];
    for (const kind of toClient) {
      expect(TITLE[kind], kind).toBeDefined();
      expect(messages[TITLE[kind]!], kind).toBeDefined();
    }
  });

  it("lleva al enlace de la API si la persona tiene el módulo", () => {
    const all = ["panel", "inbox", "reservas", "usage"] as const;
    // Spec 056 (requisitos 2.4 y 2.7): el aviso de pausa llega sin enlace, y uno
    // viejo con `/agentes` no lleva a una pantalla que ya no existe.
    expect(hrefFor(notice("agent.paused"), all)).toBeNull();
    expect(hrefFor(notice("agent.paused", { href: "/agentes" }), all)).toBeNull();
    expect(hrefFor(notice("channel.paused", { href: "/agentes" }), all)).toBeNull();
    expect(hrefFor(notice("client.wallet.empty", { href: "/usage" }), ["panel"])).toBe("/");
    expect(hrefFor(notice("inbox.waiting", { href: "/inbox?c=k1" }), all)).toBe("/inbox?c=k1");
  });

  it("los avisos de antes, sin enlace, siguen llevando donde llevaban", () => {
    expect(hrefFor(notice("inbox.waiting", { data: { conversation_id: "k 1" } }), ["inbox"])).toBe("/inbox?c=k%201");
    expect(hrefFor(notice("client.balance_out"), ["usage"])).toBe("/usage");
    expect(hrefFor(notice("member.joined"), ["usage"])).toBeNull();
  });
});
