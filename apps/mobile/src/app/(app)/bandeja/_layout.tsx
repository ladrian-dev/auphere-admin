import { Stack } from "expo-router";

import { useTabStackOptions } from "@/features/tab-stack";
import { useT } from "@/i18n/t";

/** The Bandeja's stack: the list. A conversation opens above the tabs (`app/conversacion`). */
export default function BandejaStack() {
  const t = useT();
  return (
    <Stack screenOptions={useTabStackOptions()}>
      <Stack.Screen name="index" options={{ title: t("inbox.title") }} />
    </Stack>
  );
}
