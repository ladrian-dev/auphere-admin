import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { centeredPopupFeatures, loginForCode, parseMetaSignupMessage, signupExtras, signupOutcome, withCenteredPopup } from "../meta-fb-sdk";

describe("meta-fb-sdk (CP-17)", () => {
  it("parses the JSON-string envelope Meta posts", () => {
    const raw = JSON.stringify({ type: "WA_EMBEDDED_SIGNUP", event: "FINISH", data: { waba_id: "1", phone_number_id: "2" } });
    expect(parseMetaSignupMessage(raw)?.data?.waba_id).toBe("1");
    expect(parseMetaSignupMessage({ type: "WA_EMBEDDED_SIGNUP", event: "CANCEL" })?.event).toBe("CANCEL");
  });
  it("ignores unrelated messages", () => {
    expect(parseMetaSignupMessage("not json")).toBeNull();
    expect(parseMetaSignupMessage({ type: "other" })).toBeNull();
    expect(parseMetaSignupMessage(null)).toBeNull();
  });
});

describe("registro integrado v4 y v5 (spec 050, requisito 3.1)", () => {
  const msg = (event: string, data?: Record<string, unknown>) => parseMetaSignupMessage(JSON.stringify({ type: "WA_EMBEDDED_SIGNUP", event, data }));

  it("v4: Cloud API manda solo setup; coexistencia, su featureType; nunca sessionInfoVersion", () => {
    expect(signupExtras("cloud_api")).toEqual({ setup: {} });
    expect(signupExtras("cloud_api", "v4")).toEqual({ setup: {} });
    expect(signupExtras("coexistence", "v4")).toEqual({ setup: {}, featureType: "whatsapp_business_app_onboarding" });
    for (const mode of ["cloud_api", "coexistence"] as const) {
      for (const version of ["v4", "v5"] as const) expect(signupExtras(mode, version)).not.toHaveProperty("sessionInfoVersion");
    }
  });

  it("v5: la coexistencia viene encendida, así que Cloud API la apaga", () => {
    expect(signupExtras("coexistence", "v5")).toEqual({ version: "v5" });
    expect(signupExtras("cloud_api", "v5")).toEqual({
      version: "v5",
      features: [{ name: "whatsapp_business_app_onboarding", enabled: false }],
    });
  });

  it("los dos FINISH de v4 dan los ids de la WABA", () => {
    expect(signupOutcome(msg("FINISH", { waba_id: "W1", phone_number_id: "P1", business_id: "B1" }))).toEqual({
      kind: "finished",
      waba_id: "W1",
      phone_number_id: "P1",
      business_id: "B1",
    });
    expect(signupOutcome(msg("FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING", { waba_id: "W2" }))).toEqual({
      kind: "finished",
      waba_id: "W2",
      phone_number_id: undefined,
      business_id: undefined,
    });
  });

  it("el FINISH de v5 trae la WABA en messaging_account_ids", () => {
    const out = signupOutcome(msg("FINISH", { messaging_account_ids: ["W5", "W6"], is_on_biz_app: true }));
    expect(out).toMatchObject({ kind: "finished", waba_id: "W5" });
  });

  it("FINISH_ONLY_WABA y FINISH_GRANT_ONLY_API_ACCESS dicen qué falta", () => {
    expect(signupOutcome(msg("FINISH_ONLY_WABA", { waba_id: "W1" }))).toEqual({ kind: "failed", code: "no_number" });
    expect(signupOutcome(msg("FINISH_GRANT_ONLY_API_ACCESS", { waba_id: "W1" }))).toEqual({ kind: "failed", code: "grant_only" });
  });

  it("CANCEL y ERROR terminan; un FINISH sin WABA es un error de Meta", () => {
    expect(signupOutcome(msg("CANCEL", { current_step: "PHONE_NUMBER_SETUP" }))).toEqual({ kind: "failed", code: "cancelled", detail: "PHONE_NUMBER_SETUP" });
    expect(signupOutcome(msg("ERROR", { error_message: "boom" }))).toEqual({ kind: "failed", code: "meta_error", detail: "boom" });
    expect(signupOutcome(msg("FINISH", {}))).toMatchObject({ kind: "failed", code: "meta_error" });
  });

  it("un evento desconocido o un mensaje ajeno no cierran la espera", () => {
    expect(signupOutcome(msg("STEP_CHANGED"))).toBeNull();
    expect(signupOutcome(null)).toBeNull();
  });
});

describe("la ventana de Meta, centrada (2026-09-30)", () => {
  it("las features ponen un popup de 720×780 en el centro de la pantalla", () => {
    // Chrome abría la ventana a pantalla completa con el asistente de Meta
    // acurrucado arriba a la izquierda: al SDK le faltaba `popup=yes` y un
    // tamaño. Con pantalla 1600×900 el centro es (440, 60).
    expect(centeredPopupFeatures({ width: 1600, height: 900 })).toBe(
      "popup=yes,width=720,height=780,left=440,top=60,resizable=yes,scrollbars=yes",
    );
  });

  it("en una pantalla pequeña no se sale de ella", () => {
    const f = centeredPopupFeatures({ width: 600, height: 700 });
    expect(f).toContain("width=600");
    expect(f).toContain("height=700");
    expect(f).toContain("left=0,top=0");
  });

  it("un segundo monitor desplaza el centro con él", () => {
    expect(centeredPopupFeatures({ width: 1600, height: 900, left: 1920, top: 0 })).toContain("left=2360,top=60");
  });

  it("parchea window.open solo mientras dura la llamada, y lo devuelve aunque falle", () => {
    const original = vi.fn();
    window.open = original as unknown as typeof window.open;
    withCenteredPopup(() => window.open("https://www.facebook.com/dialog", "fb", "toolbar=0,width=10,height=10"));
    expect(original).toHaveBeenCalledTimes(1);
    const features = String(original.mock.calls[0]![2]);
    expect(features).toMatch(/^popup=yes,width=\d+,height=\d+,left=\d+,top=\d+,resizable=yes,scrollbars=yes,toolbar=0$/);
    expect(window.open).toBe(original);
    expect(() =>
      withCenteredPopup(() => {
        throw new Error("boom");
      }),
    ).toThrow("boom");
    expect(window.open).toBe(original);
  });
});

/**
 * Spec 049, requisito 8: Instagram se conecta también entrando con Instagram.
 * Sin `prompt=login`, quien tiene una sesión de Facebook abierta entra con
 * ella y Meta no le ofrece Instagram (guía del inicio de sesión unificado,
 * paso 4). Messenger no lo pide.
 */
describe("prompt=login en la ventana de Meta (spec 049, requisito 8)", () => {
  type LoginCb = (r: { status?: string; authResponse?: { code?: string } }) => void;
  const login = vi.fn<(cb: LoginCb, opts: Record<string, unknown>) => void>((cb) => cb({ status: "connected", authResponse: { code: "C" } }));
  window.FB = { init: vi.fn(), login } as unknown as NonNullable<typeof window.FB>;

  it("lo pasa a FB.login cuando se le pide", async () => {
    await expect(loginForCode({ appId: "1", version: "v26.0", configId: "9", prompt: "login" })).resolves.toBe("C");
    expect(login.mock.lastCall?.[1]).toMatchObject({ config_id: "9", response_type: "code", prompt: "login" });
  });

  it("sin pedirlo, no lo manda", async () => {
    await expect(loginForCode({ appId: "1", version: "v26.0", configId: "9" })).resolves.toBe("C");
    expect(login.mock.lastCall?.[1]).not.toHaveProperty("prompt");
  });
});

/**
 * Spec 047 (30.4, T101) y spec 049 (7.2, enmienda del 2026-11-26): la espera
 * de la ventana de Meta del alta de WhatsApp siempre termina. `loginWithMeta`
 * real, con el SDK simulado en `window.FB`; cada prueba carga el módulo de
 * nuevo, porque el SDK se guarda en una variable del módulo.
 */
describe("loginWithMeta: la espera de la ventana de Meta siempre termina (047 T101; 049 7.2)", () => {
  type LoginCb = (r: { status?: string; authResponse?: { code?: string } }) => void;
  type Sdk = typeof import("../meta-fb-sdk");
  const OPTS = { appId: "1", version: "v26.0", configId: "cfg", mode: "cloud_api" as const };
  const FIVE_MIN = 5 * 60 * 1000;

  let callbacks: LoginCb[];
  let live: Set<EventListenerOrEventListenerObject>;

  async function fresh(withSdk = true): Promise<Sdk> {
    vi.resetModules();
    callbacks = [];
    if (withSdk) {
      window.FB = { init: vi.fn(), login: vi.fn((cb: LoginCb) => void callbacks.push(cb)) } as unknown as NonNullable<typeof window.FB>;
    } else {
      delete window.FB;
    }
    return import("../meta-fb-sdk");
  }

  /** Lo que Meta manda desde la ventana al terminar el asistente. */
  function finish(data: Record<string, unknown>) {
    const payload = JSON.stringify({ type: "WA_EMBEDDED_SIGNUP", event: "FINISH", data });
    window.dispatchEvent(new MessageEvent("message", { origin: "https://www.facebook.com", data: payload }));
  }

  /** Con qué SignupError termina la promesa, o «pending» si sigue esperando. */
  async function settle(p: Promise<unknown>): Promise<string> {
    let out = "pending";
    p.then(
      () => (out = "resolved"),
      (err: { code?: string }) => (out = err?.code ?? "error"),
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
    vi.useRealTimers();
  });

  it("con el código y los ids de Meta resuelve, y no deja oyente ni plazo vivos", async () => {
    const sdk = await fresh();
    const p = sdk.loginWithMeta(OPTS);
    await vi.advanceTimersByTimeAsync(0);
    finish({ waba_id: "W1", phone_number_id: "P1" });
    callbacks[0]!({ status: "connected", authResponse: { code: "C0DE" } });
    await expect(p).resolves.toEqual({ code: "C0DE", waba_id: "W1", phone_number_id: "P1", business_id: undefined });
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("si Meta no manda ninguna señal, a los 5 minutos termina con «timeout» y lo limpia todo", async () => {
    const sdk = await fresh();
    const p = sdk.loginWithMeta(OPTS);
    expect(await settle(p)).toBe("pending");
    expect(live.size).toBe(1);
    await vi.advanceTimersByTimeAsync(FIVE_MIN);
    await expect(p).rejects.toMatchObject({ code: "timeout" });
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("si el SDK de Meta no llega a cargar, el plazo corre igual", async () => {
    const sdk = await fresh(false);
    const p = sdk.loginWithMeta(OPTS);
    expect(await settle(p)).toBe("pending");
    await vi.advanceTimersByTimeAsync(FIVE_MIN);
    await expect(p).rejects.toMatchObject({ code: "timeout" });
    expect(live.size).toBe(0);
  });

  it("cerrar la ventana sin código se dice «cancelled» (la ventana se cerró), no «no_code»", async () => {
    const sdk = await fresh();
    for (const status of ["unknown", "not_authorized", undefined]) {
      const p = sdk.loginWithMeta(OPTS);
      await vi.advanceTimersByTimeAsync(0);
      callbacks.at(-1)!({ status });
      await expect(p).rejects.toMatchObject({ code: "cancelled" });
    }
    // «Conectado» y sin código es la configuración, no la persona.
    const p = sdk.loginWithMeta(OPTS);
    await vi.advanceTimersByTimeAsync(0);
    callbacks.at(-1)!({ status: "connected" });
    await expect(p).rejects.toMatchObject({ code: "no_code" });
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancelar termina la espera al momento y quita el oyente y el plazo; lo que Meta mande después no cuenta", async () => {
    const sdk = await fresh();
    const controller = new AbortController();
    const p = sdk.loginWithMeta({ ...OPTS, signal: controller.signal });
    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    await expect(p).rejects.toMatchObject({ code: "cancelled" });
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
    // Meta devuelve tarde: nada lo recoge.
    finish({ waba_id: "LATE" });
    callbacks[0]!({ status: "connected", authResponse: { code: "LATE" } });
  });

  it("cancelado antes de empezar, ni siquiera abre la ventana", async () => {
    const sdk = await fresh();
    const controller = new AbortController();
    controller.abort();
    await expect(sdk.loginWithMeta({ ...OPTS, signal: controller.signal })).rejects.toMatchObject({ code: "cancelled" });
    expect(window.FB!.login).not.toHaveBeenCalled();
    expect(live.size).toBe(0);
  });

  it("si FB.login falla al abrir la ventana, termina al momento y lo limpia todo", async () => {
    const sdk = await fresh();
    (window.FB!.login as ReturnType<typeof vi.fn>).mockImplementationOnce(() => {
      throw new Error("popup blocked");
    });
    const p = sdk.loginWithMeta(OPTS);
    expect(await settle(p)).toBe("sdk_failed");
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("un intento nuevo termina el anterior: su oyente y su plazo no siguen vivos", async () => {
    const sdk = await fresh();
    const first = sdk.loginWithMeta(OPTS);
    await vi.advanceTimersByTimeAsync(0);
    const second = sdk.loginWithMeta(OPTS);
    await expect(first).rejects.toMatchObject({ code: "cancelled" });
    await vi.advanceTimersByTimeAsync(0);
    expect(live.size).toBe(1);
    expect(vi.getTimerCount()).toBe(1);
    finish({ waba_id: "W2" });
    callbacks[1]!({ status: "connected", authResponse: { code: "SECOND" } });
    await expect(second).resolves.toMatchObject({ code: "SECOND", waba_id: "W2" });
    expect(live.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});
