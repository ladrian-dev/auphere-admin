import { describe, expect, it } from "vitest";

import type { SendReadinessOut, TenantHealth } from "@/lib/backend";

import { readinessChecks, sendReadinessChecks } from "../readiness";

const health: TenantHealth = {
  tenant_id: "t1",
  channels_active: 1,
  channels_attention: 0,
  primary_channel: { type: "whatsapp", identifier: "+569", status: "active" },
  agent_version: 4,
  open_conversations: 0,
  conversations_7d: 0,
  last_message_at: null,
  connectors_attention: 0,
};

describe("what a client still needs (spec 036, R3)", () => {
  it("everything done", () => {
    const checks = readinessChecks({ base: "/tenants/t1", tenant: { owner_phone: "+56911" }, health, brokenConnectors: [] });
    expect(checks.every((c) => c.ok)).toBe(true);
    expect(checks.map((c) => c.key)).toEqual(["agent", "channel", "owner", "connectors"]);
  });

  it("names the next step as an action, and where to do it", () => {
    const checks = readinessChecks({
      base: "/tenants/t1",
      tenant: { owner_phone: null },
      health: { ...health, channels_active: 0, agent_version: null },
      brokenConnectors: ["Calendly"],
    });
    expect(checks.filter((c) => !c.ok).map((c) => c.label)).toEqual([
      "Publicar el agente",
      "Conectar un canal",
      "Añadir el teléfono del dueño",
      "Reconectar conectores",
    ]);
    expect(checks.find((c) => c.key === "channel")?.href).toBe("/tenants/t1/channels/new");
    expect(checks.find((c) => c.key === "connectors")?.detail).toContain("Calendly");
  });

  it("a failing channel sends to its list, not to add another", () => {
    const channel = readinessChecks({
      base: "/tenants/t1",
      tenant: { owner_phone: "+569" },
      health: { ...health, channels_active: 0, channels_attention: 1 },
      brokenConnectors: [],
    }).find((c) => c.key === "channel");
    expect(channel?.action).toBe("Revisar canal");
    expect(channel?.href).toBe("/tenants/t1/channels");
  });
});

describe("a send-only client's setup (spec 077, 1.4)", () => {
  const ready: SendReadinessOut = {
    channel: { ok: true, active_numbers: 1 },
    template: { ok: true, approved: 1, pending: 0, unknown: false },
    membership: { ok: true, status: "active" },
    keys: { ok: true, active: 1 },
  };

  it("four steps, in the order of the setup, all done", () => {
    const steps = sendReadinessChecks({ base: "/tenants/t1", readiness: ready });
    expect(steps.map((s) => s.key)).toEqual(["channel", "template", "membership", "keys"]);
    expect(steps.every((s) => s.state === "done")).toBe(true);
  });

  it("without a membership there is no membership step", () => {
    const steps = sendReadinessChecks({ base: "/tenants/t1", readiness: { ...ready, membership: null } });
    expect(steps.map((s) => s.key)).toEqual(["channel", "template", "keys"]);
  });

  it("a template Meta did not answer about is neither ready nor pending", () => {
    const template = sendReadinessChecks({
      base: "/tenants/t1",
      readiness: { ...ready, template: { ok: false, approved: 0, pending: 0, unknown: true } },
    }).find((s) => s.key === "template");
    expect(template?.state).toBe("unknown");
    expect(template?.ok).toBe(false);
    expect(template?.detail).toContain("No se pudo comprobar");
  });

  it("names each missing step as an action, and where to do it", () => {
    const steps = sendReadinessChecks({
      base: "/tenants/t1",
      readiness: {
        channel: { ok: false, active_numbers: 0 },
        template: { ok: false, approved: 0, pending: 0, unknown: false },
        membership: { ok: false, status: "pending" },
        keys: { ok: false, active: 0 },
      },
      membership: { amount_cents: 4000, payer: "stripe" },
    });
    expect(steps.every((s) => s.state === "todo")).toBe(true);
    const by = Object.fromEntries(steps.map((s) => [s.key, s]));
    expect(by.channel.action).toBe("Enviar enlace");
    expect(by.channel.href).toBe("/tenants/t1/channels/new/whatsapp");
    // The template is created on the number: with no number there is nowhere to go yet.
    expect(by.template.href).toBeUndefined();
    expect(by.membership.action).toBe("Crear enlace de pago");
    expect(by.membership.detail).toContain("por Stripe");
    expect(by.keys.action).toBe("Crear clave");
    expect(by.keys.href).toBe("/tenants/t1/api");
  });

  it("a template in review is pending, and says so", () => {
    const template = sendReadinessChecks({
      base: "/tenants/t1",
      readiness: { ...ready, template: { ok: false, approved: 0, pending: 1, unknown: false } },
    }).find((s) => s.key === "template");
    expect(template?.state).toBe("todo");
    expect(template?.detail).toContain("en revisión");
  });

  it("an active membership whose period is over does not count as ready", () => {
    const step = sendReadinessChecks({
      base: "/tenants/t1",
      readiness: { ...ready, membership: { ok: false, status: "active" } },
    }).find((s) => s.key === "membership");
    expect(step?.ok).toBe(false);
    expect(step?.detail).toContain("no envía");
  });
});
