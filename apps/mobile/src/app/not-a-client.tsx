import { router } from "expo-router";

import { EntryFrame } from "@/features/entry";
import { useT } from "@/i18n/t";
import { Button } from "@/ui/button";

/** R1.5: a partner member signed in. The app is for the businesses Auphere serves, not for partners. */
export default function NotAClient() {
  const t = useT();
  return (
    <EntryFrame title={t("app.notClient.title")} body={t("app.notClient.body")}>
      <Button label={t("app.other")} variant="secondary" full onPress={() => router.replace("/sign-in")} />
    </EntryFrame>
  );
}
