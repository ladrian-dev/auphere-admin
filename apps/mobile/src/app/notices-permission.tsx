import { router } from "expo-router";
import { StyleSheet, View } from "react-native";

import { useMe } from "@/api/hooks";
import { markNoticesAsked } from "@/auth/store";
import { EntryFrame } from "@/features/entry";
import { permissionLines } from "@/features/notices";
import { useT, type T } from "@/i18n/t";
import { usePush } from "@/push/provider";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * Before the system's dialog (031 R10.1; spec 044, R14.4): what a notice looks
 * like — an example, with what it would say — then what we notify about, one
 * line per kind of the client's modules (Reservas' three said as one), and
 * nothing else. «Activar avisos» and «Ahora no» are pinned under what scrolls,
 * so declining is always in sight (closes 042 H15); «Ahora no» does not
 * trigger the dialog. Shown once after the first sign-in on this phone;
 * Ajustes turns notices on later (031 R10.2).
 */
export default function NoticesPermission() {
  const t = useT();
  const { colors } = useTheme();
  const push = usePush();
  const me = useMe();
  const lines = permissionLines(me.data?.nav ?? []);

  const done = async (enable: boolean) => {
    await markNoticesAsked();
    if (enable) await push.enable();
    if (router.canGoBack()) router.back();
  };

  const lead = (
    <View style={styles.lead}>
      <ExampleNotice t={t} />
      <Text variant="body" tone="mutedForeground">
        {t("avisos.permission.body")}
      </Text>
      <View style={styles.kinds}>
        {lines.map((k) => (
          <View key={k.key} style={styles.kind} accessible accessibilityLabel={`${t(k.label)}. ${t(k.hint)}`}>
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
    </View>
  );

  return (
    <EntryFrame
      title={t("avisos.permission.title")}
      lead={lead}
      footer={
        <>
          <Button label={t("app.notices.allow")} full onPress={() => void done(true)} testID="notices-allow" />
          <Button label={t("app.notices.later")} variant="ghost" full onPress={() => void done(false)} testID="notices-later" />
        </>
      }
    >
      <Text variant="footnote" tone="mutedForeground">
        {t("app.notices.privacy")}
      </Text>
    </EntryFrame>
  );
}

/**
 * A notice as the phone would show it: the app, when, who and why — the same
 * minimum the API sends (031 R8.3). Opaque, like any content; it is a picture
 * of a notice, so the screen reader hears it once, as an example.
 */
function ExampleNotice({ t }: { t: T }) {
  const { colors } = useTheme();
  const title = t("avisos.example.title");
  const body = t("avisos.example.body");
  return (
    <View
      accessible
      accessibilityLabel={t("avisos.example.a11y", { title, body })}
      style={[styles.example, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: CARD_RADIUS + 6 }]}
    >
      <View style={[styles.appIcon, { backgroundColor: colors.brandGround }]}>
        <Icon name={icons.hand} size={16} tone="accentSoft" />
      </View>
      <View style={styles.text}>
        <View style={styles.exampleHead}>
          <Text variant="caption" tone="mutedForeground" style={styles.text} numberOfLines={1}>
            {t("avisos.example.app")}
          </Text>
          <Text variant="caption" tone="mutedForeground">
            {t("avisos.example.when")}
          </Text>
        </View>
        <Text variant="bodyStrong">{title}</Text>
        <Text variant="callout" tone="mutedForeground">
          {body}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  lead: { gap: 16 },
  kinds: { gap: 14 },
  kind: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  icon: { width: 36, height: 36, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  text: { flex: 1, minWidth: 0, gap: 2 },
  example: { flexDirection: "row", gap: 10, padding: 12, borderWidth: StyleSheet.hairlineWidth * 2 },
  appIcon: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  exampleHead: { flexDirection: "row", gap: 8, alignItems: "baseline" },
});
