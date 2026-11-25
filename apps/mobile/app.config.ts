import { existsSync } from "node:fs";

import type { ConfigContext, ExpoConfig } from "expo/config";

import { tokens } from "./src/theme/tokens.gen.ts";

/**
 * Auphere Customers — spec 031.
 *
 * One app, four EAS profiles (`eas.json`): `development` (dev client against
 * the local stack), `preview` (an internal install against staging), `staging`
 * (a store build against staging, for TestFlight and Play's internal testing)
 * and `production`. Only `development` changes the identifier (`.dev`); the
 * others are the same app. What changes between them comes from the
 * environment, never from editing this file:
 *
 * - The EAS project (`eas init`, 2026-10-20): `@lmatos/auphere-customers`.
 *   Fixed below because they are identifiers, not secrets; `EAS_PROJECT_ID` /
 *   `EAS_OWNER` still override them, for the move to Auphere's account.
 * - `EXPO_PUBLIC_API_URL` / `EXPO_PUBLIC_CONSOLE_URL`: where it talks to.
 * - `GOOGLE_SERVICES_JSON`: the Firebase file for FCM, as an EAS file secret.
 *
 * The app has its own sign-in (email and password, or Google through the API;
 * R1 as amended on 2026-10-20). Google's window returns through the custom
 * scheme (`auphere-customers://auth/callback`), which PKCE and `state` protect;
 * the universal link (`applinks:`) is deferred (contracts/phone-auth.md).
 */
const projectId = process.env.EAS_PROJECT_ID ?? "15621aff-af18-43b6-917c-6df25f22e737";
const owner = process.env.EAS_OWNER ?? "lmatos";
const variant = process.env.APP_VARIANT ?? "production";
const dev = variant === "development";

/**
 * Spec 069 (D3, R1.4–R1.5): Helvena, the brand's face, in titles and figures.
 * Its app licence was confirmed by Luis on 2026-11-21, so every build embeds
 * its three static faces from `assets/fonts/helvena/` (versioned). A local
 * build can ask for the system font with `APP_HELVENA=0`, to measure it
 * (R22). Embedded by the expo-font plugin at build time: nothing loads at run
 * time. A missing face stops the build rather than shipping without the brand.
 */
const HELVENA_DIR = "./assets/fonts/helvena";
const HELVENA_FACES = [
  { file: "Helvena-Regular.ttf", weight: 400 },
  { file: "Helvena-Medium.ttf", weight: 500 },
  { file: "Helvena-Semibold.ttf", weight: 600 },
] as const;
const helvena = process.env.APP_HELVENA !== "0";
const missingFace = HELVENA_FACES.find((f) => !existsSync(`${__dirname}/assets/fonts/helvena/${f.file}`));
if (helvena && missingFace) throw new Error(`Helvena: ${HELVENA_DIR}/${missingFace.file} is missing (spec 069, R1.4).`);

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: dev ? "Customers Dev" : "Auphere Customers",
  slug: "auphere-customers",
  // A phone app: no web build (Metro would try to bundle one for a browser).
  platforms: ["ios", "android"],
  owner,
  // Spec 047 (T171, 50.8): 1.2.0 brings Agentes, Negocio and «Corregir esta respuesta» through the stores —
  // new screens and new data shown are never sent over the air (D19). `runtimeVersion` follows it, so no
  // 1.1.0 install gets 1.2.0's code. Spec 044 (D14): 1.1.0 carried spec 042's native module.
  // Spec 069 (R22.1): the new design, with SVG and Skia, comes as 1.3.0 through the stores only.
  version: "1.3.0",
  orientation: "portrait",
  icon: "./assets/images/icon.png",
  scheme: "auphere-customers",
  userInterfaceStyle: "automatic",
  backgroundColor: tokens.light.background,
  ios: {
    bundleIdentifier: dev ? "com.auphere.customers.dev" : "com.auphere.customers",
    supportsTablet: false,
    icon: "./assets/images/icon.png",
    infoPlist: {
      ITSAppUsesNonExemptEncryption: false,
      NSCameraUsageDescription: "Para enviar una foto a un cliente desde la Bandeja.",
      NSPhotoLibraryUsageDescription: "Para enviar una imagen de tu galería a un cliente desde la Bandeja.",
      CFBundleAllowMixedLocalizations: true,
    },
    entitlements: {
      // R8.8: «espera a una persona» atraviesa los modos de concentración.
      "com.apple.developer.usernotifications.time-sensitive": true,
    },
  },
  android: {
    package: dev ? "com.auphere.customers.dev" : "com.auphere.customers",
    adaptiveIcon: {
      backgroundColor: tokens.light.brandGround,
      foregroundImage: "./assets/images/android-icon-foreground.png",
      monochromeImage: "./assets/images/android-icon-monochrome.png",
    },
    ...(process.env.GOOGLE_SERVICES_JSON ? { googleServicesFile: process.env.GOOGLE_SERVICES_JSON } : {}),
    // Nothing the app does needs the microphone or the location.
    blockedPermissions: ["android.permission.RECORD_AUDIO", "android.permission.ACCESS_FINE_LOCATION"],
    predictiveBackGestureEnabled: false,
  },
  locales: { es: "./locales/es.json", en: "./locales/en.json" },
  plugins: [
    "expo-router",
    [
      "expo-splash-screen",
      {
        image: "./assets/images/splash-icon.png",
        imageWidth: 88,
        backgroundColor: tokens.light.background,
        dark: { image: "./assets/images/splash-icon.png", backgroundColor: tokens.dark.background },
      },
    ],
    ["expo-secure-store", { configureAndroidBackup: true }],
    "expo-localization",
    "expo-web-browser",
    [
      "expo-notifications",
      {
        icon: "./assets/images/notification-icon.png",
        color: tokens.light.primaryDeep,
        defaultChannel: "messages_v1",
      },
    ],
    [
      "expo-image-picker",
      {
        photosPermission: "Para enviar una imagen de tu galería a un cliente desde la Bandeja.",
        cameraPermission: "Para enviar una foto a un cliente desde la Bandeja.",
        microphonePermission: false,
      },
    ],
    [
      "expo-build-properties",
      {
        // iOS 16.4+ (plan). Android keeps Expo 58's SDK levels (compile 37), above Play's floor.
        ios: { deploymentTarget: "16.4" },
      },
    ],
    ...(helvena
      ? [
          [
            "expo-font",
            {
              android: {
                fonts: [
                  {
                    fontFamily: "Helvena",
                    fontDefinitions: HELVENA_FACES.map((f) => ({ path: `${HELVENA_DIR}/${f.file}`, weight: f.weight })),
                  },
                ],
              },
              ios: { fonts: HELVENA_FACES.map((f) => `${HELVENA_DIR}/${f.file}`) },
            },
          ] as [string, Record<string, unknown>],
        ]
      : []),
  ],
  // D19: OTA only for fixes, one channel per profile; the native runtime is the app version.
  runtimeVersion: { policy: "appVersion" },
  updates: { url: `https://u.expo.dev/${projectId}` },
  experiments: { typedRoutes: true, reactCompiler: true },
  extra: { eas: { projectId }, variant, helvena },
});
