import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../connector-actions");
const quality = await import("../model-quality-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const CONN = "33333333-3333-4333-8333-333333333331";
const ids = { ref: "demo", agent: AGENT };

/**
 * Spec 047 (historias 21 y 23; T129 y T147) — las acciones de los Conectores
 * de un agente, de la página de cada conexión y de Calidad: `agents:read` para
 * leer, `agents:write` para lo demás; la forma del contrato se comprueba antes
 * de llegar a la API y sus códigos vuelven tal cual.
 */
describe("los conectores de un agente", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("conectar manda el conector, el agente y el permiso; el formulario de clave vuelve con su código", async () => {
    await actions.connectConnectorAction({ ...ids, slug: "woocommerce", permission: "ask_before_write" });
    expect(h.backend.connectConnector).toHaveBeenCalledWith("demo", { integration: "woocommerce", agent_id: AGENT, permission: "ask_before_write" });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
    h.fail("connectConnector", 409, "", "authorize_with_form", { auth_kind: "api_key", form: [{ field: "token" }] });
    expect(await actions.connectConnectorAction({ ...ids, slug: "woocommerce", permission: "read" })).toMatchObject({
      ok: false,
      code: "authorize_with_form",
      info: { auth_kind: "api_key", form: [{ field: "token" }] },
    });
  });

  it("el permiso y los ajustes, quitarlo y leer el catálogo", async () => {
    await actions.setActivationAction({ ...ids, slug: "woocommerce", permission: "read_write", settings: { store_url: "https://t.example" } });
    expect(h.backend.setActivation).toHaveBeenCalledWith("demo", AGENT, "woocommerce", { permission: "read_write", settings: { store_url: "https://t.example" } });
    await actions.setActivationAction({ ...ids, slug: "woocommerce", permission: "read" });
    expect(h.backend.setActivation).toHaveBeenLastCalledWith("demo", AGENT, "woocommerce", { permission: "read", settings: {} });
    h.fail("setActivation", 422, "", "invalid_settings", { errors: [{ field: "store_url", message: "x" }] });
    expect(await actions.setActivationAction({ ...ids, slug: "woocommerce", permission: "read", settings: { store_url: "x" } })).toMatchObject({ code: "invalid_settings" });
    await actions.removeActivationAction({ ...ids, slug: "woocommerce" });
    expect(h.backend.removeActivation).toHaveBeenCalledWith("demo", AGENT, "woocommerce");
    await actions.agentConnectorsAction(ids);
    expect(h.backend.listAgentConnectors).toHaveBeenCalledWith("demo", AGENT);
  });

  it("la página de la conexión: leer, reconectar y «Desconectar para todos» con su confirmación", async () => {
    await actions.connectionPageAction({ ref: "demo", connection: CONN });
    expect(h.backend.getConnectionPage).toHaveBeenCalledWith("demo", CONN);
    await actions.reconnectConnectionAction({ ref: "demo", connection: CONN });
    expect(h.backend.reconnectConnection).toHaveBeenCalledWith("demo", CONN);
    h.fail("disconnectConnection", 409, "", "confirm_required", { affected: [] });
    expect(await actions.disconnectConnectionAction({ ref: "demo", connection: CONN, confirm: false })).toMatchObject({ code: "confirm_required", info: { affected: [] } });
    expect(h.backend.disconnectConnection).toHaveBeenCalledWith("demo", CONN, false);
  });

  it("una forma que no es la del contrato no llega a la API", async () => {
    await expect(actions.connectConnectorAction({ ...ids, slug: "Woo Commerce", permission: "read" })).rejects.toThrow();
    await expect(actions.connectConnectorAction({ ...ids, slug: "woocommerce", permission: "admin" })).rejects.toThrow();
    await expect(actions.setActivationAction({ ...ids, agent: "nadie", slug: "woocommerce", permission: "read" })).rejects.toThrow();
    await expect(actions.disconnectConnectionAction({ ref: "demo", connection: CONN })).rejects.toThrow();
    expect(h.backend.connectConnector).not.toHaveBeenCalled();
    expect(h.backend.setActivation).not.toHaveBeenCalled();
  });

  it("un analista lee el catálogo y la página, pero no cambia nada", async () => {
    h.setRole("analyst");
    expect(await actions.agentConnectorsAction(ids)).toMatchObject({ ok: true });
    expect(await actions.connectionPageAction({ ref: "demo", connection: CONN })).toMatchObject({ ok: true });
    for (const write of [
      actions.connectConnectorAction({ ...ids, slug: "woocommerce", permission: "read" }),
      actions.setActivationAction({ ...ids, slug: "woocommerce", permission: "read" }),
      actions.removeActivationAction({ ...ids, slug: "woocommerce" }),
      actions.reconnectConnectionAction({ ref: "demo", connection: CONN }),
      actions.disconnectConnectionAction({ ref: "demo", connection: CONN, confirm: true }),
    ]) {
      expect(await write).toEqual(h.denied());
    }
    expect(h.backend.disconnectConnection).not.toHaveBeenCalled();
  });
});

describe("Calidad del agente", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("leer y comprobar una política con la forma del esquema", async () => {
    await quality.modelQualityAction(ids);
    expect(h.backend.getModelQuality).toHaveBeenCalledWith("demo", AGENT);
    await quality.checkModelQualityAction({ ...ids, policy: { kind: "pinned", deployment: "anthropic/claude-sonnet-eu" } });
    expect(h.backend.checkModelQuality).toHaveBeenCalledWith("demo", AGENT, { kind: "pinned", deployment: "anthropic/claude-sonnet-eu" });
    h.fail("checkModelQuality", 402, "", "build_budget_exhausted");
    expect(await quality.checkModelQualityAction({ ...ids, policy: { kind: "profile", profile: "max" } })).toMatchObject({ status: 402, code: "build_budget_exhausted" });
    await expect(quality.checkModelQualityAction({ ...ids, policy: { kind: "profile", profile: "turbo" } })).rejects.toThrow();
  });

  it("un analista lee la calidad pero no la comprueba", async () => {
    h.setRole("analyst");
    expect(await quality.modelQualityAction(ids)).toMatchObject({ ok: true });
    expect(await quality.checkModelQualityAction({ ...ids, policy: { kind: "profile", profile: "auto" } })).toEqual(h.denied());
    expect(h.backend.checkModelQuality).not.toHaveBeenCalled();
  });
});
