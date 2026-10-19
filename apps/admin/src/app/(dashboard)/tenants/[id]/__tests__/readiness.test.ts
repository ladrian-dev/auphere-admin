import { describe, expect, it } from "vitest";

import type { TenantHealth } from "@/lib/backend";

import { readinessChecks } from "../readiness";

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
