import { describe, expect, it } from "vitest";

import type { TenantHealth } from "@/lib/backend";

import { compareRows, inView, isQuiet, reasonsFor } from "../health";

const healthy: TenantHealth = {
  tenant_id: "t",
  channels_active: 1,
  channels_attention: 0,
  primary_channel: { type: "whatsapp", identifier: "+569", status: "active" },
  agent_version: 2,
  open_conversations: 0,
  conversations_7d: 3,
  last_message_at: new Date().toISOString(),
  connectors_attention: 0,
};

describe("client health (spec 036, R2)", () => {
  it("a client that serves needs nothing", () => {
    expect(reasonsFor({ status: "active" }, healthy)).toEqual([]);
  });

  it("says each reason in words", () => {
    const keys = reasonsFor(
      { status: "active" },
      { ...healthy, channels_active: 0, channels_attention: 1, agent_version: null, connectors_attention: 1 },
    ).map((r) => r.label);
    expect(keys).toEqual(["Canal con problemas", "Conector por reconectar", "Agente sin publicar"]);
    expect(reasonsFor({ status: "active" }, { ...healthy, channels_active: 0 }).map((r) => r.key)).toEqual(["no_channel"]);
  });

  it("notices a client gone quiet, and leaves paused and archived alone", () => {
    const old = new Date(Date.now() - 20 * 86_400_000).toISOString();
    expect(isQuiet({ ...healthy, last_message_at: old })).toBe(true);
    expect(isQuiet(healthy)).toBe(false);
    // Quiet is a hint, not a reason to need attention.
    expect(reasonsFor({ status: "active" }, { ...healthy, last_message_at: old })).toEqual([]);
    expect(reasonsFor({ status: "paused" }, { ...healthy, agent_version: null })).toEqual([]);
    expect(reasonsFor({ status: "provisioning" }, undefined)[0]?.label).toBe("A medio montar");
  });

  it("keeps archived clients out of the default view", () => {
    expect(inView("all", { status: "archived" }, [])).toBe(false);
    expect(inView("archived", { status: "archived" }, [])).toBe(true);
    expect(inView("attention", { status: "active" }, [{ key: "x", label: "x", tone: "warning" }])).toBe(true);
  });

  it("puts what broke first, then what waits, then the rest by name", () => {
    const rows = [
      { tenant: { name: "Beta" }, reasons: [] },
      { tenant: { name: "Alfa" }, reasons: [{ key: "a", label: "a", tone: "warning" as const }] },
      { tenant: { name: "Zeta" }, reasons: [{ key: "b", label: "b", tone: "danger" as const }] },
      { tenant: { name: "Alba" }, reasons: [] },
    ];
    expect([...rows].sort(compareRows("attention")).map((r) => r.tenant.name)).toEqual(["Zeta", "Alfa", "Alba", "Beta"]);
    expect([...rows].sort(compareRows("name")).map((r) => r.tenant.name)).toEqual(["Alba", "Alfa", "Beta", "Zeta"]);
  });
});
