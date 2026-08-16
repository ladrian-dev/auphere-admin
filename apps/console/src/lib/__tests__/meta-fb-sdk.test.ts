import { describe, expect, it } from "vitest";

import { loginExtras, parseMetaSignupMessage } from "../meta-fb-sdk";

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
