import { isLiquidGlassAvailable } from "expo-glass-effect";
import { Platform } from "react-native";

/**
 * Whether the system draws Liquid Glass here (spec 042, R1.1, R3.1): iOS 26
 * and up, and nowhere else. What a person asked for in accessibility
 * («Reducir transparencia») is a separate question, answered live by
 * `useSystemAppearance()`; this one is fixed for the life of the process.
 */
export function glassAvailable(): boolean {
  return Platform.OS === "ios" && isLiquidGlassAvailable();
}
