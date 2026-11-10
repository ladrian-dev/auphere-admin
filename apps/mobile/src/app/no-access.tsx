import { router } from "expo-router";

import { EntryFrame } from "@/features/entry";
import { useT } from "@/i18n/t";
import { Button } from "@/ui/button";

/** R1.5: the business has no Lite Console, or this person no longer belongs to it. */
export default function NoAccess() {
  const t = useT();
  return (
    <EntryFrame title={t("app.noAccess.title")} body={t("app.noAccess.body")}>
      <Button label={t("app.other")} variant="secondary" full onPress={() => router.replace("/sign-in")} />
    </EntryFrame>
  );
}
