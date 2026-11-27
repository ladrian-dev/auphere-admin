/**
 * Spec 047 (30.4, T101) y spec 049 (7.2, enmienda del 2026-11-26): el panel
 * abre la misma ventana de Meta que la consola, y su espera también termina.
 * `loginWithMeta` real del panel con el SDK simulado en `window.FB`. El módulo
 * lee `NEXT_PUBLIC_META_APP_ID` al cargarse y guarda el SDK en una variable,
 * así que cada prueba fija el entorno y lo carga de nuevo.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type LoginCb = (r: { status?: string; authResponse?: { code?: string } }) => void;
type Sdk = typeof import("../meta-fb-sdk");

const FIVE_MIN = 5 * 60 * 1000;

let callbacks: LoginCb[];
let live: Set<EventListenerOrEventListenerObject>;

async function fresh(withSdk = true): Promise<Sdk> {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_META_APP_ID", "1");
  callbacks = [];
  if (withSdk) {
    window.FB = { init: vi.fn(), login: vi.fn((cb: LoginCb) => void callbacks.push(cb)) } as unknown as NonNullable<typeof window.FB>;
  } else {
    delete window.FB;
  }
  return import("../meta-fb-sdk");
}

function finish(data: Record<string, unknown>) {
  const payload = JSON.stringify({ type: "WA_EMBEDDED_SIGNUP", event: "FINISH", data });
  window.dispatchEvent(new MessageEvent("message", { origin: "https://www.facebook.com", data: payload }));
}

async function settle(p: Promise<unknown>): Promise<string> {
  let out = "pending";
  p.then(
    () => (out = "resolved"),
    (err: Error) => (out = err.message),
  );
  await vi.advanceTimersByTimeAsync(0);
  return out;
}

beforeEach(() => {
  vi.useFakeTimers();
  live = new Set();
  const add = window.addEventListener.bind(window);
  const remove = window.removeEventListener.bind(window);
  vi.spyOn(window, "addEventListener").mockImplementation((type, fn, opts) => {
    if (type === "message") live.add(fn);
    add(type, fn, opts);
  });
  vi.spyOn(window, "removeEventListener").mockImplementation((type, fn, opts) => {
    if (type === "message") live.delete(fn);
    remove(type, fn, opts);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

describe("panel: la espera de la ventana de Meta siempre termina (047 T101; 049 7.2)", () => {
  it("con el código y los ids resuelve, sin oyente ni plazo vivos", async () => {
    const sdk = await fresh();
    const p = sdk.loginWithMeta("cfg", "cloud_api");
    await vi.advanceTimersByTimeAsync(0);
    callbacks[0]!({ status: "connected", authResponse: { code: "C0DE" } });
    finish({ waba_id: "W1" });
    await expect(p).resolves.toMatchObject({ code: "C0DE", waba_id: "W1" });
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("si Meta no manda ninguna señal, a los 5 minutos termina y lo limpia todo", async () => {
    const sdk = await fresh();
    const p = sdk.loginWithMeta("cfg", "cloud_api");
    expect(await settle(p)).toBe("pending");
    await vi.advanceTimersByTimeAsync(FIVE_MIN);
    await expect(p).rejects.toThrow(/Meta no respondió a tiempo/);
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("si el SDK no llega a cargar, el plazo corre igual", async () => {
    const sdk = await fresh(false);
    const p = sdk.loginWithMeta("cfg", "cloud_api");
    expect(await settle(p)).toBe("pending");
    await vi.advanceTimersByTimeAsync(FIVE_MIN);
    await expect(p).rejects.toThrow(/Meta no respondió a tiempo/);
  });

  it("cerrar la ventana sin código dice que se cerró la ventana", async () => {
    const sdk = await fresh();
    const p = sdk.loginWithMeta("cfg", "cloud_api");
    await vi.advanceTimersByTimeAsync(0);
    callbacks[0]!({ status: "unknown" });
    await expect(p).rejects.toThrow("Se cerró la ventana de Meta antes de terminar. No se conectó nada.");
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancelar termina la espera al momento y no deja oyente ni plazo", async () => {
    const sdk = await fresh();
    const controller = new AbortController();
    const p = sdk.loginWithMeta("cfg", "cloud_api", "v4", controller.signal);
    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    await expect(p).rejects.toThrow(/Se canceló/);
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("si FB.login falla al abrir la ventana, termina al momento y lo limpia todo", async () => {
    const sdk = await fresh();
    (window.FB!.login as ReturnType<typeof vi.fn>).mockImplementationOnce(() => {
      throw new Error("popup blocked");
    });
    const p = sdk.loginWithMeta("cfg", "cloud_api");
    expect(await settle(p)).toBe("popup blocked");
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("un intento nuevo termina el anterior", async () => {
    const sdk = await fresh();
    const first = sdk.loginWithMeta("cfg", "cloud_api");
    await vi.advanceTimersByTimeAsync(0);
    const second = sdk.loginWithMeta("cfg", "coexistence");
    await expect(first).rejects.toThrow(/Se canceló/);
    await vi.advanceTimersByTimeAsync(0);
    expect(live.size).toBe(1);
    expect(vi.getTimerCount()).toBe(1);
    callbacks[1]!({ status: "connected", authResponse: { code: "SECOND" } });
    finish({ waba_id: "W2" });
    await expect(second).resolves.toMatchObject({ code: "SECOND", waba_id: "W2" });
    expect(live.size).toBe(0);
  });
});
