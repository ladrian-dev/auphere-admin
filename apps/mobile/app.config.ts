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
 * - `EAS_PROJECT_ID` / `EAS_OWNER`: the FACELAD Expo account for now (D21).
 *   The owner runs `eas init` once and sets them; until then the app still
 *   builds locally (`expo run:*`), it just has no OTA channel.
 * - `EXPO_PUBLIC_API_URL` / `EXPO_PUBLIC_CONSOLE_URL`: where it talks to.
 * - `GOOGLE_SERVICES_JSON`: the Firebase file for FCM, as an EAS file secret.
 *
 * The app has its own sign-in (email and password, or Google through the API;
 * R1 as amended on 2026-10-20). Google's window returns through the custom
 * scheme (`auphere-customers://auth/callback`), which PKCE and `state` protect;
 * the universal link (`applinks:`) is deferred (contracts/phone-auth.md).
 */
const projectId = process.env.EAS_PROJECT_ID;
const variant = process.env.APP_VARIANT ?? "production";
const dev = variant === "development";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: dev ? "Customers Dev" : "Auphere Customers",
  slug: "auphere-customers",
  // A phone app: no web build (Metro would try to bundle one for a browser).
  platforms: ["ios", "android"],
  ...(process.env.EAS_OWNER ? { owner: process.env.EAS_OWNER } : {}),
  version: "1.0.0",
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
  ],
  // D19: OTA only for fixes, one channel per profile; the native runtime is the app version.
  runtimeVersion: { policy: "appVersion" },
  ...(projectId ? { updates: { url: `https://u.expo.dev/${projectId}` } } : {}),
  experiments: { typedRoutes: true, reactCompiler: true },
  extra: { ...(projectId ? { eas: { projectId } } : {}), variant },
});
