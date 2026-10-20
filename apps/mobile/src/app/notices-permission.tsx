import { router } from "expo-router";
import { StyleSheet, View } from "react-native";

import { useMe } from "@/api/hooks";
import { markNoticesAsked } from "@/auth/store";
import { EntryFrame } from "@/features/entry";
import { kindsFor } from "@/features/notices";
import { useT } from "@/i18n/t";
import { usePush } from "@/push/provider";
import { useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * Before the system's dialog (R10.1): what we notify about, and nothing else,
 * with «Ahora no» that does not trigger the dialog. Shown once after the first
 * sign-in on this phone; Ajustes turns notices on later (R10.2).
 */
export default function NoticesPermission() {
  const t = useT();
  const { colors } = useTheme();
  const push = usePush();
  const me = useMe();
  const kinds = kindsFor(me.data?.nav ?? []);

  const done = async (enable: boolean) => {
    await markNoticesAsked();
    if (enable) await push.enable();
    if (router.canGoBack()) router.back();
  };

  const list = (
    <View style={styles.kinds}>
      {kinds.map((k) => (
        <View key={k.kind} style={styles.kind} accessible accessibilityLabel={`${t(k.label)}. ${t(k.hint)}`}>
          <View style={[styles.icon, { backgroundColor: colors.positiveBg }]}>
            <Icon name={k.icon} size={18} tone="primaryText" />
          </View>
          <View style={styles.text}>
            <Text variant="bodyStrong">{t(k.label)}</Text>
            <Text variant="footnote" tone="mutedForeground">
              {t(k.hint)}
            </Text>
          </View>
        </View>
      ))}
    </View>
  );

  return (
    <EntryFrame title={t("app.notices.title")} body={t("app.notices.body")} lead={list}>
      <Text variant="footnote" tone="mutedForeground">
        {t("app.notices.privacy")}
      </Text>
      <Button label={t("app.notices.allow")} full onPress={() => void done(true)} testID="notices-allow" />
      <Button label={t("app.notices.later")} variant="ghost" full onPress={() => void done(false)} testID="notices-later" />
    </EntryFrame>
  );
}

const styles = StyleSheet.create({
  kinds: { gap: 14, paddingTop: 8 },
  kind: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  icon: { width: 36, height: 36, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  text: { flex: 1, minWidth: 0, gap: 2 },
});
