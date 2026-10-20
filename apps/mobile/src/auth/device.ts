import * as Device from "expo-device";

import { PLATFORM } from "@/config";

/**
 * How this phone is named in «Tus teléfonos» (R2.4): its model («iPhone 15»,
 * «Pixel 9»), never anything the person typed. Trimmed to 80 like the API.
 */
export function displayName(): string {
  const name = Device.modelName ?? (PLATFORM === "ios" ? "iPhone" : "Android");
  return name.slice(0, 80);
}
