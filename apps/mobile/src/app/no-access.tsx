import { router } from "expo-router";

import { EntryFrame } from "@/features/entry";
import { useT } from "@/i18n/t";
import { Button } from "@/ui/button";
import { icons } from "@/ui/icon";

/**
 * R1.5: the business has no Lite Console, or this person no longer belongs to
 * it. Spec 069: the design's look — a tile, the title, whom to ask — and the
 * way back, in the footbar.
 */
export default function NoAccess() {
  const t = useT();
  return (
    <EntryFrame
      title={t("app.noAccess.title")}
      body={t("app.noAccess.body")}
      icon={{ name: icons.lock, tone: "wait" }}
      footer={<Button label={t("app.other")} variant="secondary" full onPress={() => router.replace("/sign-in")} />}
    />
  );
}
