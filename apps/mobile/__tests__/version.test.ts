import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Spec 044, Requisito 19, research D14: a native runtime that follows the
 * version — 1.0.0 in TestFlight has no `expo-glass-effect` (spec 042), so no
 * update over the air may ever reach it — and the builds for TestFlight and
 * Play's internal track. Spec 047 (T171, 50.8): Agentes, Negocio and the
 * corrections are new screens and new data, so they come as 1.2.0 through the
 * stores; over the air only fixes. Spec 069 (Requisito 22.1): the new design and its
 * native modules (SVG, Skia) come as 1.3.0, through the stores only.
 */
const ROOT = join(__dirname, "..");
const read = (f: string) => readFileSync(join(ROOT, f), "utf8");
const eas = JSON.parse(read("eas.json")) as {
  build: Record<string, { android?: { buildType?: string }; channel?: string; extends?: string; env?: Record<string, string> }>;
  submit: Record<string, { ios?: { ascAppId?: string }; android?: { track?: string } }>;
};

describe("the app's version (R19.1)", () => {
  it("is 1.3.0 in the app config and in package.json (spec 069, R22.1)", () => {
    expect(read("app.config.ts")).toMatch(/version: "1\.3\.0"/);
    expect((JSON.parse(read("package.json")) as { version: string }).version).toBe("1.3.0");
  });

  it("the native runtime follows the version, so an older install gets nothing of 1.3.0 over the air", () => {
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

  // What a profile inherits counts too (`extends`, /cso L3).
  const envOf = (p: string): Record<string, string> => {
    const b = eas.build[p];
    return b ? { ...(b.extends ? envOf(b.extends) : {}), ...(b.env ?? {}) } : {};
  };

  it("no store build carries the example data of Reservas (R18.2) or of the whole app (069 R23.2)", () => {
    for (const p of ["preview", "staging", "production"]) {
      const env = envOf(p);
      expect(env.EXPO_PUBLIC_RESERVAS_DEMO).toBeUndefined();
      expect(env.EXPO_PUBLIC_DEMO).toBeUndefined();
    }
  });

  it("every build carries Helvena (069 R1.4–R1.5, licence confirmed by Luis on 2026-11-21): its three faces are versioned and nothing switches it off", () => {
    for (const face of ["Regular", "Medium", "Semibold"]) {
      expect(existsSync(join(ROOT, `assets/fonts/helvena/Helvena-${face}.ttf`))).toBe(true);
    }
    for (const p of ["development", "preview", "staging", "production"]) expect(envOf(p).APP_HELVENA).toBeUndefined();
    // On unless a local build asks for the system font by hand (`APP_HELVENA=0`, to measure it).
    expect(read("app.config.ts")).toMatch(/process\.env\.APP_HELVENA !== "0"/);
    expect(read(".gitignore")).not.toMatch(/assets\/fonts\/helvena/);
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
