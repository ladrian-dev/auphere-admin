import { Stack } from "expo-router";

import { useTabStackOptions } from "@/features/tab-stack";

/** A native stack inside the tab: large title on iOS, the platform's own header on Android (R14.8). */
export default function TabStack() {
  return <Stack screenOptions={useTabStackOptions()} />;
}
