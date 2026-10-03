import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const {
  connectApiKeyAction,
  connectorStatusAction,
  setAgendaProUrlAction,
  startConsentAction,
  syncConnectorAction,
} = await import("../actions");

/**
 * Integraciones (spec 017, R4). Vienen de `tools/actions.ts`, con los mismos
 * casos de la spec 016 y uno nuevo que es el motivo de haberlas movido:
 * revalidan la ficha entera, no su pestaña.
 */
describe("integrations actions (spec 017, R4)", () => {
  it("conectar revalida la ficha entera, no solo esta pestaña (R4.3)", async () => {
    h.setRole("owner");
    h.backend.connectApiKey.mockResolvedValueOnce({ slug: "woocommerce", status: "connected" });
    await connectApiKeyAction({
      ref: "demo",
      slug: "woocommerce",
      secrets: { consumer_key: "ck" },
      endpoint_meta: { store_url: "https://s" },
    });
    // Capacidades vive en otra ruta de la misma ficha: si solo se revalidara
    // `/integrations`, seguiría diciendo que lo que depende de WooCommerce no
    // funciona hasta que alguien recargara a mano.
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalledWith("/clients/demo/integrations");
  });

  it("setAgendaProUrlAction enlaza y desenlaza por la misma llamada", async () => {
    h.setRole("builder");
    const out = {
      integration: "agendapro",
      public_url: "https://x.site.agendapro.com/cl/s",
      updated_at: "2026-09-23T00:00:00Z",
    };
    h.backend.setAgendaProUrl.mockResolvedValueOnce(out);
    expect(await setAgendaProUrlAction({ ref: "demo", public_url: out.public_url })).toEqual({
      ok: true,
      data: out,
    });
    expect(h.backend.setAgendaProUrl).toHaveBeenCalledWith("demo", out.public_url);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");

    h.backend.setAgendaProUrl.mockResolvedValueOnce({ ...out, public_url: null });
    expect(await setAgendaProUrlAction({ ref: "demo", public_url: null })).toMatchObject({
      ok: true,
      data: { public_url: null },
    });

    h.fail("setAgendaProUrl", 422, "", "invalid_url");
    expect(
      await setAgendaProUrlAction({ ref: "demo", public_url: "https://evil.example" }),
    ).toMatchObject({ ok: false, code: "invalid_url" });
  });

  it("connectApiKeyAction devuelve el conector con el resultado del sync", async () => {
    h.setRole("owner");
    const out = {
      slug: "woocommerce",
      status: "connected",
      last_sync: { status: "error", reason: "provider_unavailable", added: 0, deprecated: 0, at: "x" },
    };
    h.backend.connectApiKey.mockResolvedValueOnce(out);
    const res = await connectApiKeyAction({
      ref: "demo",
      slug: "woocommerce",
      secrets: { consumer_key: "ck" },
      endpoint_meta: { store_url: "https://s" },
    });
    expect(res).toEqual({ ok: true, data: out });
    expect(h.backend.connectApiKey).toHaveBeenCalledWith("demo", "woocommerce", {
      secrets: { consumer_key: "ck" },
      endpoint_meta: { store_url: "https://s" },
    });
  });

  it("ninguna escritura de integración pasa sin agents:write, y ninguna llega al backend", async () => {
    h.setRole("analyst");
    const names = [
      "startConsent",
      "syncConnector",
      "pauseConnector",
      "resumeConnector",
      "disconnectConnector",
      "connectApiKey",
      "setAgendaProUrl",
    ] as const;
    for (const n of names) h.backend[n].mockClear();

    expect(await startConsentAction({ ref: "demo", slug: "googlecalendar" })).toEqual(h.denied());
    expect(await syncConnectorAction({ ref: "demo", slug: "googlecalendar" })).toEqual(h.denied());
    for (const op of ["pause", "resume", "disconnect"] as const) {
      expect(await connectorStatusAction({ ref: "demo", slug: "googlecalendar", op })).toEqual(
        h.denied(),
      );
    }
    expect(
      await connectApiKeyAction({ ref: "demo", slug: "woocommerce", secrets: { k: "v" }, endpoint_meta: {} }),
    ).toEqual(h.denied());
    expect(await setAgendaProUrlAction({ ref: "demo", public_url: null })).toEqual(h.denied());

    for (const n of names) expect(h.backend[n]).not.toHaveBeenCalled();
  });
});
