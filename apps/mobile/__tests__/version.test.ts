import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Spec 044, Requisito 19, research D14: version 1.1.0 and a native runtime
 * that follows it — 1.0.0 in TestFlight has no `expo-glass-effect` (spec 042),
 * so no update over the air may ever reach it — and the builds for TestFlight
 * and Play's internal track.
 */
const ROOT = join(__dirname, "..");
const read = (f: string) => readFileSync(join(ROOT, f), "utf8");
const eas = JSON.parse(read("eas.json")) as {
  build: Record<string, { android?: { buildType?: string }; channel?: string; env?: Record<string, string> }>;
  submit: Record<string, { ios?: { ascAppId?: string }; android?: { track?: string } }>;
};

describe("the app's version (R19.1)", () => {
  it("is 1.1.0 in the app config and in package.json", () => {
    expect(read("app.config.ts")).toMatch(/version: "1\.1\.0"/);
    expect((JSON.parse(read("package.json")) as { version: string }).version).toBe("1.1.0");
  });

  it("the native runtime follows the version, so 1.0.0 gets nothing over the air", () => {
    expect(read("app.config.ts")).toMatch(/runtimeVersion: \{ policy: "appVersion" \}/);
  });
});

describe("the builds (R19.2)", () => {
  it("preview is an APK to install by hand; staging goes to TestFlight and to Play's internal track", () => {
    expect(eas.build.preview?.android?.buildType).toBe("apk");
    expect(eas.build.staging?.android?.buildType).toBe("app-bundle");
    expect(eas.submit.staging?.ios?.ascAppId).toBe("6825002452");
    expect(eas.submit.staging?.android?.track).toBe("internal");
  });

  it("no store build carries the example data of Reservas (R18.2)", () => {
    for (const p of ["preview", "staging", "production"]) expect(eas.build[p]?.env?.EXPO_PUBLIC_RESERVAS_DEMO).toBeUndefined();
  });
});

describe("the locale files (R19.2, first Android release build)", () => {
  it.each(["es", "en"])("keep the iOS strings under «ios», so Android's release lint does not reject them (%s)", (lang) => {
    // A flat key goes to both platforms: Android wrote CFBundleDisplayName and the usage strings into
    // values-b+<lang>/strings.xml, missing from the default locale, and `lintVitalRelease` failed the AAB.
    const locale = JSON.parse(read(`locales/${lang}.json`)) as Record<string, unknown>;
    expect(Object.keys(locale).filter((k) => k !== "ios" && k !== "android")).toEqual([]);
    expect(locale.ios).toMatchObject({ CFBundleDisplayName: "Customers" });
  });
});
