import Constants from "expo-constants";
import { Platform } from "react-native";

/**
 * Where the app talks to, and who it says it is (spec 031, contracts/phone-auth.md).
 *
 * `EXPO_PUBLIC_*` are inlined at build time per EAS profile (`eas.json`). A
 * dev build without them talks to the machine it was built on: the Android
 * emulator reaches the host at 10.0.2.2, the iOS simulator at localhost.
 */
const devHost = Platform.OS === "android" ? "10.0.2.2" : "localhost";

const trim = (url: string) => url.replace(/\/+$/, "");

export const API_URL = trim(process.env.EXPO_PUBLIC_API_URL ?? (__DEV__ ? `http://${devHost}:8000` : "https://api.auphere.com"));
export const CONSOLE_URL = trim(
  process.env.EXPO_PUBLIC_CONSOLE_URL ?? (__DEV__ ? `http://${devHost}:3110` : "https://console.auphere.com"),
);

export const APP_VERSION = Constants.expoConfig?.version ?? "0.0.0";
export const PLATFORM: "ios" | "android" = Platform.OS === "ios" ? "ios" : "android";
export const VARIANT = String(Constants.expoConfig?.extra?.variant ?? "production");

/** The only way back from Google's window: fixed on the API too (`api/app_public.py`). */
export const AUTH_REDIRECT = "auphere-customers://auth/callback";

/** Store pages, for «Actualizar» (R13.1). The App Store id exists once the app is created. */
export const STORE_URL =
  PLATFORM === "android"
    ? "market://details?id=com.auphere.customers"
    : process.env.EXPO_PUBLIC_APP_STORE_ID
      ? `itms-apps://apps.apple.com/app/id${process.env.EXPO_PUBLIC_APP_STORE_ID}`
      : "https://apps.apple.com/search?term=Auphere%20Customers";
