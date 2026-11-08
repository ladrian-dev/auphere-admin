import { describe, expect, it } from "vitest";

import { messages, type MessageKey } from "@/i18n/messages";
import type { ClientAccess, ClientAccessMember } from "@/lib/backend/client-access";

import { accessBody, accessErrorKey, personRowLayout, personStatus, revokeCopy } from "../access-model";

const person = (over: Partial<ClientAccessMember> = {}): ClientAccessMember => ({
  id: "m1",
  kind: "member",
  email: "ana@negocio.test",
  name: "Ana",
  status: "active",
  ...over,
});

const access = (over: Partial<ClientAccess> = {}): ClientAccess => ({
  eligible: true,
  ineligible_reason: null,
  whatsapp_connected: true,
  enabled: true,
  modules: ["panel"],
  members: [],
  reservas: null,
  ...over,
});

/**
 * Spec 056 (requisito 3.5; guías de Apple): una sola acción a la vista por fila,
 * la principal para su estado, y el resto en «⋯» con «Revocar» al final.
 */
describe("personRowLayout", () => {
  it("una invitación pendiente: Reenviar a la vista, Revocar en el menú", () => {
    expect(personRowLayout(person({ kind: "invitation", status: "pending" }))).toEqual({ primary: "resend", menu: ["revoke"] });
  });

  it("una invitación caducada: Reenviar, sin menú", () => {
    expect(personRowLayout(person({ kind: "invitation", status: "expired" }))).toEqual({ primary: "resend", menu: [] });
  });

  it("una persona activa: nada a la vista, Revocar en el menú", () => {
    expect(personRowLayout(person())).toEqual({ primary: null, menu: ["revoke"] });
  });

  it("lo revocado no tiene acciones", () => {
    expect(personRowLayout(person({ status: "revoked" }))).toEqual({ primary: null, menu: [] });
    expect(personRowLayout(person({ kind: "invitation", status: "revoked" }))).toEqual({ primary: null, menu: [] });
  });

  it("Revocar va siempre la última", () => {
    for (const m of [person(), person({ kind: "invitation", status: "pending" })]) {
      const { menu } = personRowLayout(m);
      expect(menu[menu.length - 1]).toBe("revoke");
    }
  });
});

describe("personStatus", () => {
  it("dice invitada, activa, caducada o revocada (3.4)", () => {
    expect(personStatus(person({ kind: "invitation", status: "pending" }))).toEqual({ key: "clientAccess.status.pending", tone: "info" });
    expect(personStatus(person())).toEqual({ key: "clientAccess.status.active", tone: "positive" });
    expect(personStatus(person({ kind: "invitation", status: "expired" }))).toEqual({ key: "clientAccess.status.expired", tone: "warn" });
    expect(personStatus(person({ status: "revoked" }))).toEqual({ key: "clientAccess.status.revoked", tone: "muted" });
    for (const s of ["pending", "active", "expired", "revoked"]) expect(messages[`clientAccess.status.${s}` as MessageKey]).toBeDefined();
  });
});

describe("accessBody", () => {
  it("manda los módulos en el orden de la barra y solo los cuatro de hoy", () => {
    expect(accessBody(access(), { enabled: true, modules: new Set(["usage", "panel", "inbox"]), mode: null, kind: null })).toEqual({
      enabled: true,
      modules: ["panel", "inbox", "usage"],
    });
  });

  it("Reservas lleva su modo la primera vez, y en Aforo su tipo", () => {
    expect(accessBody(access(), { enabled: true, modules: new Set(["reservas"]), mode: "capacity", kind: "bar" })).toEqual({
      enabled: true,
      modules: ["reservas"],
      reservas: { mode: "capacity", capacity_kind: "bar" },
    });
  });

  it("sin cambiar de modo no se vuelven a mandar los ajustes de Reservas", () => {
    const stored = access({
      modules: ["reservas"],
      reservas: { mode: "services", capacity_kind: null, live_future: 0, agents_pending_promotion: [] },
    });
    expect(accessBody(stored, { enabled: true, modules: new Set(["reservas", "panel"]), mode: "services", kind: null })).toEqual({
      enabled: true,
      modules: ["panel", "reservas"],
    });
  });

  it("con reservas vivas, solo tras decidirlo se manda `cancel_and_notify`", () => {
    const stored = access({
      modules: ["reservas"],
      reservas: { mode: "capacity", capacity_kind: "bar", live_future: 3, agents_pending_promotion: [] },
    });
    expect(accessBody(stored, { enabled: true, modules: new Set(["reservas"]), mode: "services", kind: null }, "cancel_and_notify")).toEqual({
      enabled: true,
      modules: ["reservas"],
      reservas: { mode: "services", on_live: "cancel_and_notify" },
    });
  });
});

describe("accessErrorKey", () => {
  it("cada código de la API tiene su frase, y uno desconocido la genérica", () => {
    for (const code of [
      "no_modules",
      "inbox_requires_whatsapp",
      "unknown_module",
      "reservas_mode_required",
      "reservas_kind_required",
      "live_reservations",
      "access_disabled",
      "account_is_partner_member",
      "account_is_other_client",
      "already_member",
      "not_an_invitation",
      "unknown_member",
      "rate_limited",
      "archived",
    ]) {
      const key = accessErrorKey(code);
      expect(key, code).toBe(`clientAccess.error.${code}`);
      expect(messages[key], code).toBeDefined();
    }
    expect(accessErrorKey("lo_que_sea")).toBe("clientAccess.error.generic");
    expect(accessErrorKey(null)).toBe("clientAccess.error.generic");
  });
});

describe("revokeCopy", () => {
  it("una persona pierde el acceso, una invitación deja de servir", () => {
    expect(revokeCopy(person())).toEqual({ title: "clientAccess.revoke.member.title", body: "clientAccess.revoke.member.body" });
    expect(revokeCopy(person({ kind: "invitation", status: "pending" }))).toEqual({
      title: "clientAccess.revoke.invitation.title",
      body: "clientAccess.revoke.invitation.body",
    });
  });
});
