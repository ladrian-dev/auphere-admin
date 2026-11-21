import { router } from "expo-router";

import { EntryFrame } from "@/features/entry";
import { useT } from "@/i18n/t";
import { Button } from "@/ui/button";
import { icons } from "@/ui/icon";

/**
 * R1.5: a partner member signed in. The app is for the businesses Auphere
 * serves, not for partners (spec 031, 2026-10-20: nothing here leads to the
 * partner console). Spec 069: the design's look — the building in the amber of
 * attention, not of danger — and the way back, in the footbar.
 */
export default function NotAClient() {
  const t = useT();
  return (
    <EntryFrame
      title={t("app.notClient.title")}
      body={t("app.notClient.body")}
      icon={{ name: icons.building, tone: "wait" }}
      footer={<Button label={t("app.other")} variant="secondary" full onPress={() => router.replace("/sign-in")} />}
    />
  );
}
