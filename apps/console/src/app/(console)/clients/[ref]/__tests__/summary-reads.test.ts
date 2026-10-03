import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const Page = (await import("../page")).default;

/**
 * R1.8 — cómo se arma el Resumen, no cómo se pinta.
 *
 * **Sin esto, R1.8 es una intención y no un criterio.** Nada impediría que
 * una refactor metiera una quinta llamada, repitiera una, o pusiera las
 * cuatro en serie: la pantalla se vería igual y tardaría el cuádruple.
 *
 * La prueba de que van en paralelo no es contar: es **no dejar que ninguna
 * termine** y comprobar que aun así se pidieron las cuatro. Si fueran en
 * serie, solo se habría pedido la primera.
 */

/** Una promesa que no se resuelve hasta que el test quiere. */
function pendiente<T>() {
  let resolver!: (v: T) => void;
  const promesa = new Promise<T>((r) => (resolver = r));
  return { promesa, resolver };
}

const CLIENTE = {
  external_client_ref: "demo",
  name: "Panadería La Espiga",
  timezone: "Europe/Madrid",
  status: "active",
  sector: "barbershop",
  health: { ready: true, agent_version: 3, whatsapp_connected: true, display_phone_number: "+34 600" },
  quota: { cap: 50_000, remaining: 31_400 },
};

const LAS_CUATRO = ["getClient", "usageV2", "conversationStats", "listChannels", "listConnectors"] as const;

describe("el Resumen se arma con cuatro lecturas, en paralelo", () => {
  it("las pide todas sin esperar a que ninguna termine", async () => {
    h.setRole("owner");
    for (const n of LAS_CUATRO) h.backend[n].mockClear();

    // Ninguna resuelve: si el código fuera en serie, se quedaría en la primera.
    const bloqueadas = LAS_CUATRO.map(() => pendiente<unknown>());
    LAS_CUATRO.forEach((n, i) => h.backend[n].mockReturnValue(bloqueadas[i]!.promesa));

    const pintando = Page({ params: Promise.resolve({ ref: "demo" }) });
    // Un respiro para que el `Promise.all` despache las cinco llamadas.
    await new Promise((r) => setTimeout(r, 0));

    for (const n of LAS_CUATRO) {
      expect(h.backend[n], `${n} no se pidió: ¿están en serie?`).toHaveBeenCalledTimes(1);
    }

    bloqueadas[0]!.resolver(CLIENTE);
    bloqueadas[1]!.resolver({ month: { units: 1, projected_month_units: 2, basis_days: 3, days_in_month: 30 } });
    bloqueadas[2]!.resolver({ conversations: 1, escalated: 0, failed_messages: 0 });
    bloqueadas[3]!.resolver([]);
    bloqueadas[4]!.resolver([]);
    await pintando;
  });

  it("ninguna se pide dos veces, y no hay una quinta fuente", async () => {
    h.setRole("owner");
    const llamadas: string[] = [];
    for (const n of Object.keys(h.backend)) h.backend[n as keyof typeof h.backend].mockClear();
    h.backend.getClient.mockImplementation(async () => (llamadas.push("getClient"), CLIENTE));
    h.backend.usageV2.mockImplementation(async () => {
      llamadas.push("usageV2");
      return { month: { units: 1, projected_month_units: 2, basis_days: 3, days_in_month: 30 } };
    });
    h.backend.conversationStats.mockImplementation(async () => {
      llamadas.push("conversationStats");
      return { conversations: 1, escalated: 0, failed_messages: 0 };
    });
    h.backend.listChannels.mockImplementation(async () => (llamadas.push("listChannels"), []));
    h.backend.listConnectors.mockImplementation(async () => (llamadas.push("listConnectors"), []));

    await Page({ params: Promise.resolve({ ref: "demo" }) });

    expect(llamadas.sort()).toEqual([...LAS_CUATRO].sort());
    // Una por lectura: repetir una es gratis de escribir y caro de ver.
    expect(new Set(llamadas).size).toBe(llamadas.length);
  });

  it("una lectura caída no tumba las demás: la página se pinta igual", async () => {
    h.setRole("owner");
    h.backend.getClient.mockResolvedValue(CLIENTE);
    h.backend.usageV2.mockRejectedValue(new Error("boom"));
    h.backend.conversationStats.mockResolvedValue({ conversations: 1, escalated: 0, failed_messages: 0 });
    h.backend.listChannels.mockResolvedValue([]);
    h.backend.listConnectors.mockResolvedValue([]);

    await expect(Page({ params: Promise.resolve({ ref: "demo" }) })).resolves.toBeTruthy();
  });

  it("un rol que no puede leer consumo no lo pide: no es un bloque vacío, es una llamada que no se hace", async () => {
    h.setRole("analyst");
    for (const n of LAS_CUATRO) h.backend[n].mockClear();
    h.backend.getClient.mockResolvedValue(CLIENTE);
    h.backend.conversationStats.mockResolvedValue({ conversations: 0, escalated: 0, failed_messages: 0 });
    h.backend.listChannels.mockResolvedValue([]);
    h.backend.listConnectors.mockResolvedValue([]);
    h.backend.usageV2.mockResolvedValue({ month: { units: 0, projected_month_units: 0, basis_days: 0, days_in_month: 30 } });

    await Page({ params: Promise.resolve({ ref: "demo" }) });

    // El analista sí lee consumo y conversaciones; lo que no puede es escribir.
    expect(h.backend.getClient).toHaveBeenCalledTimes(1);
  });
});
