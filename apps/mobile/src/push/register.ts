import * as Notifications from "expo-notifications";

import { endpoints } from "@/api/endpoints";
import { PLATFORM, VARIANT } from "@/config";

/**
 * Tell the API where this phone gets its notices (R8.2): the APNs or FCM
 * device token, straight from the system — no relay. A dev client talks to
 * APNs' sandbox; every other build, to production.
 */
export async function registerDevice(token?: Notifications.DevicePushToken): Promise<boolean> {
  try {
    const device = token ?? (await Notifications.getDevicePushTokenAsync());
    await endpoints.registerPush({
      provider: PLATFORM === "ios" ? "apns" : "fcm",
      token: String(device.data),
      apns_environment: PLATFORM === "ios" ? (VARIANT === "development" ? "sandbox" : "production") : null,
    });
    return true;
  } catch {
    // No token (a build without Firebase, a simulator) or no network: the
    // next launch tries again. Nothing here is the person's to fix.
    return false;
  }
}
