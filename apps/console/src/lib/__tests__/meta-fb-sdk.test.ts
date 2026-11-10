import { describe, expect, it, vi } from "vitest";

import { centeredPopupFeatures, parseMetaSignupMessage, signupExtras, signupOutcome, withCenteredPopup } from "../meta-fb-sdk";

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
