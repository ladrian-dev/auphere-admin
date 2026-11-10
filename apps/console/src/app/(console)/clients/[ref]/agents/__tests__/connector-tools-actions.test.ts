import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../connector-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const ids = { ref: "demo", agent: AGENT };

/**
 * «Herramientas» de un conector: `agents:read` para leer, `agents:write` para
 * cambiar, y cambiar es la misma puerta que Habilidades, una herramienta por
 * llamada y siempre del agente de la ruta. Sus códigos vuelven tal cual.
 */
describe("las herramientas de un conector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("leer manda el conector, el agente y el idioma", async () => {
    await actions.connectorToolsAction({ ...ids, slug: "googlecalendar", lang: "en" });
    expect(h.backend.connectorTools).toHaveBeenCalledWith("demo", AGENT, "googlecalendar", "en");
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalled();
  });

  it("cambiar es un cambio por llamada, y refresca la ficha", async () => {
    await actions.setConnectorToolAction({ ...ids, key: "GOOGLECALENDAR_CREATE_EVENT", enabled: false });
    expect(h.backend.setCapability).toHaveBeenCalledWith("demo", { key: "GOOGLECALENDAR_CREATE_EVENT", kind: "tool", enabled: false }, AGENT);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
  });

  it("sus códigos vuelven tal cual para que la pantalla los diga con palabras", async () => {
    h.fail("setCapability", 422, "", "tool_in_use", { locked_by: "promise" });
    expect(await actions.setConnectorToolAction({ ...ids, key: "X", enabled: false })).toMatchObject({
      ok: false,
      code: "tool_in_use",
      info: { locked_by: "promise" },
    });
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalled();
  });

  it("quien solo puede leer no cambia nada, y la forma se comprueba antes de llegar a la API", async () => {
    h.setRole("analyst");
    expect(await actions.setConnectorToolAction({ ...ids, key: "X", enabled: true })).toEqual(h.denied());
    expect(h.backend.setCapability).not.toHaveBeenCalled();
    await expect(actions.connectorToolsAction({ ...ids, slug: "NO VALE", lang: "es" })).rejects.toThrow();
    await expect(actions.connectorToolsAction({ ...ids, slug: "ok", lang: "fr" })).rejects.toThrow();
  });
});
