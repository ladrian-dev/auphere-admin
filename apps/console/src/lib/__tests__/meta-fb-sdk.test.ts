import { describe, expect, it, vi } from "vitest";

import { centeredPopupFeatures, loginExtras, parseMetaSignupMessage, withCenteredPopup } from "../meta-fb-sdk";

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
  it("featureType differentiates coexistence from cloud api", () => {
    expect(loginExtras("cloud_api").featureType).toBe("");
    expect(loginExtras("coexistence").featureType).toBe("whatsapp_business_app_onboarding");
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
