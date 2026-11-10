import { Linking } from "react-native";

import { useSession } from "@/auth/session";
import { STORE_URL } from "@/config";
import { EntryFrame, EntryNotice } from "@/features/entry";
import { useT } from "@/i18n/t";
import { Button } from "@/ui/button";

/** R13.1: this version is retired. Nothing else is reachable until it is updated. */
export default function UpdateRequired() {
  const t = useT();
  const { state } = useSession();
  const reason = state.status === "update-required" ? state.reason : null;
  return (
    <EntryFrame title={t("app.update.title")} body={t("app.update.body")} notice={reason ? <EntryNotice text={reason} /> : null}>
      <Button label={t("app.update.cta")} full onPress={() => void Linking.openURL(STORE_URL)} />
    </EntryFrame>
  );
}
