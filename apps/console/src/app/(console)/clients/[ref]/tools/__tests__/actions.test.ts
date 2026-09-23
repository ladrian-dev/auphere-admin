import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { connectApiKeyAction, connectorStatusAction, resetToolModeAction, saveToolsAction, setAgendaProUrlAction, setToolModeAction, startConsentAction, syncConnectorAction } = await import("../actions");

describe("tools actions (spec 016, R6/R7 + R8)", () => {
  it("setAgendaProUrlAction links and unlinks through the same call", async () => {
    h.setRole("builder");
    const out = { integration: "agendapro", public_url: "https://x.site.agendapro.com/cl/s", updated_at: "2026-09-23T00:00:00Z" };
    h.backend.setAgendaProUrl.mockResolvedValueOnce(out);
    expect(await setAgendaProUrlAction({ ref: "demo", public_url: out.public_url })).toEqual({ ok: true, data: out });
    expect(h.backend.setAgendaProUrl).toHaveBeenCalledWith("demo", out.public_url);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/tools");
    h.backend.setAgendaProUrl.mockResolvedValueOnce({ ...out, public_url: null });
    expect(await setAgendaProUrlAction({ ref: "demo", public_url: null })).toMatchObject({ ok: true, data: { public_url: null } });
    h.fail("setAgendaProUrl", 422, "", "invalid_url");
    expect(await setAgendaProUrlAction({ ref: "demo", public_url: "https://evil.example" })).toMatchObject({ ok: false, code: "invalid_url" });
  });
  it("connectApiKeyAction returns the connector with the sync outcome", async () => {
    h.setRole("owner");
    const out = { slug: "woocommerce", status: "connected", last_sync: { status: "error", reason: "provider_unavailable", added: 0, deprecated: 0, at: "x" } };
    h.backend.connectApiKey.mockResolvedValueOnce(out);
    const res = await connectApiKeyAction({ ref: "demo", slug: "woocommerce", secrets: { consumer_key: "ck" }, endpoint_meta: { store_url: "https://s" } });
    expect(res).toEqual({ ok: true, data: out });
    expect(h.backend.connectApiKey).toHaveBeenCalledWith("demo", "woocommerce", { secrets: { consumer_key: "ck" }, endpoint_meta: { store_url: "https://s" } });
  });
  it("every tools action is denied without agents:write, before any call", async () => {
    h.setRole("analyst");
    const names = ["putTools", "putToolMode", "deleteToolMode", "startConsent", "syncConnector", "pauseConnector", "connectApiKey", "setAgendaProUrl"] as const;
    for (const n of names) h.backend[n].mockClear();
    expect(await saveToolsAction({ ref: "demo", tools: [] })).toEqual(h.denied());
    expect(await setToolModeAction({ ref: "demo", tool: "x", mode: "always" })).toEqual(h.denied());
    expect(await resetToolModeAction({ ref: "demo", tool: "x" })).toEqual(h.denied());
    expect(await startConsentAction({ ref: "demo", slug: "googlecalendar" })).toEqual(h.denied());
    expect(await syncConnectorAction({ ref: "demo", slug: "googlecalendar" })).toEqual(h.denied());
    expect(await connectorStatusAction({ ref: "demo", slug: "googlecalendar", op: "pause" })).toEqual(h.denied());
    expect(await connectApiKeyAction({ ref: "demo", slug: "woocommerce", secrets: { k: "v" }, endpoint_meta: {} })).toEqual(h.denied());
    expect(await setAgendaProUrlAction({ ref: "demo", public_url: null })).toEqual(h.denied());
    for (const n of names) expect(h.backend[n]).not.toHaveBeenCalled();
  });
});
