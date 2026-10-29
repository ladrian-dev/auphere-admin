/**
 * Spec 050 (requisito 3.1): the panel and the console open the same
 * Embedded Signup. Their SDK helpers are separate files (each app builds on
 * its own), so this compares the pure part of both on every case Meta can
 * send: if one changes without the other, this fails.
 */
import path from "node:path";

import { describe, expect, it } from "vitest";

import * as admin from "../meta-fb-sdk";

// A computed path so the panel's type check does not pull in the console's
// file (both declare ``window.FB`` with their own types).
const CONSOLE_SDK = path.resolve(__dirname, "../../../../console/src/lib/meta-fb-sdk.ts");

const MESSAGES = [
  { event: "FINISH", data: { waba_id: "W1", phone_number_id: "P1", business_id: "B1" } },
  { event: "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING", data: { waba_id: "W2" } },
  { event: "FINISH", data: { messaging_account_ids: ["W5"], is_on_biz_app: true } },
  { event: "FINISH", data: {} },
  { event: "FINISH_ONLY_WABA", data: { waba_id: "W1" } },
  { event: "FINISH_GRANT_ONLY_API_ACCESS", data: { waba_id: "W1" } },
  { event: "CANCEL", data: { current_step: "PHONE_NUMBER_SETUP" } },
  { event: "ERROR", data: { error_message: "boom" } },
  { event: "STEP_CHANGED" },
].map((m) => JSON.stringify({ type: "WA_EMBEDDED_SIGNUP", ...m }));

describe("panel y consola: el mismo registro integrado (spec 050)", () => {
  it("los mismos extras en v4 y v5, Cloud API y coexistencia", async () => {
    const consoleSdk = (await import(/* @vite-ignore */ CONSOLE_SDK)) as typeof admin;
    for (const mode of ["cloud_api", "coexistence"] as const) {
      for (const version of ["v4", "v5"] as const) {
        expect(admin.signupExtras(mode, version)).toEqual(consoleSdk.signupExtras(mode, version));
      }
    }
    expect(admin.signupExtras("cloud_api")).toEqual({ setup: {} });
  });

  it("el mismo desenlace para cada evento de Meta", async () => {
    const consoleSdk = (await import(/* @vite-ignore */ CONSOLE_SDK)) as typeof admin;
    for (const raw of MESSAGES) {
      expect(admin.signupOutcome(admin.parseMetaSignupMessage(raw))).toEqual(
        consoleSdk.signupOutcome(consoleSdk.parseMetaSignupMessage(raw)),
      );
    }
    expect(admin.signupOutcome(admin.parseMetaSignupMessage(MESSAGES[2]))).toMatchObject({ kind: "finished", waba_id: "W5" });
  });
});
