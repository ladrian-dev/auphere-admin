import { GlassView } from "expo-glass-effect";
import { router } from "expo-router";
import { useState } from "react";
import { Platform, StyleSheet, View } from "react-native";

import { useMe } from "@/api/hooks";
import { markNoticesAsked } from "@/auth/store";
import { EntryFrame } from "@/features/entry";
import { permissionLines } from "@/features/notices";
import { useT, type T } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { usePush } from "@/push/provider";
import { glassAvailable } from "@/theme/glass";
import { useSystemAppearance } from "@/theme/system-appearance";
import { RADII, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * Before the system's dialog (031 R10.1; spec 044, R14.4; spec 069, R7): a
 * real example of the urgent notice, then what we notify about, one line per
 * kind of the client's modules (Reservas' three said as one), each with when
 * it arrives, and nothing else. «Activar avisos» opens the system's own
 * permission (R7.2), never an imitation; a «no» is told it can be changed in
 * Ajustes and the app goes on (R7.3). «Activar avisos» and «Ahora no» are
 * pinned under what scrolls, so declining is always in sight (closes 042 H15);
 * «Ahora no» does not trigger the dialog. Shown once after the first sign-in
 * on this phone; Ajustes turns notices on later (031 R10.2).
 */
export default function NoticesPermission() {
  const t = useT();
  const push = usePush();
  const me = useMe();
  const lines = permissionLines(me.data?.nav ?? []);
  const [asking, setAsking] = useState(false);
  const [denied, setDenied] = useState(false);

  const close = () => {
    if (router.canGoBack()) router.back();
  };
  const later = async () => {
    haptics.light();
    await markNoticesAsked();
    close();
  };
  const enable = async () => {
    setAsking(true);
    await markNoticesAsked();
    const answer = await push.enable();
    setAsking(false);
    if (answer === "granted") {
      haptics.success();
      close();
      return;
    }
    // Not now, or never asked again by the system: say where to change it, and let the person go on.
    haptics.light();
    setDenied(true);
  };

  const lead = (
    <View style={styles.lead}>
      <ExampleNotice t={t} />
      <Text variant="subhead" tone="mutedForeground">
        {t("avisos.permission.body")}
      </Text>
      <View style={styles.kinds}>
        {lines.map((k) => {
          const urgent = k.key === "inbox.waiting";
          return (
            <View key={k.key} style={styles.kind} accessible accessibilityLabel={`${t(k.label)}. ${t(k.hint)}`}>
              <KindTile urgent={urgent} icon={k.icon} />
              <View style={styles.text}>
                <Text variant="bodyStrong">{t(k.label)}</Text>
                <Text variant="footnote" tone="mutedForeground">
                  {t(k.hint)}
                </Text>
              </View>
            </View>
          );
        })}
      </View>
      <Text variant="footnote" tone="mutedForeground">
        {t("v13.entrar.notices.later")}
      </Text>
    </View>
  );

  return (
    <EntryFrame
      title={t("avisos.permission.title")}
      lead={lead}
      footer={
        denied ? (
          <>
            <View accessible accessibilityRole="alert" accessibilityLiveRegion="polite" style={styles.denied}>
              <Icon name={icons.bellOff} size={18} tone="mutedForeground" />
              <Text variant="callout" tone="foreground" style={styles.text}>
                {t("v13.entrar.notices.denied")}
              </Text>
            </View>
            <Button label={t("v13.entrar.notices.continue")} full onPress={close} testID="notices-continue" />
          </>
        ) : (
          <>
            <Button label={t("app.notices.allow")} full busy={asking} onPress={() => void enable()} testID="notices-allow" />
            <Button label={t("app.notices.later")} variant="ghost" full disabled={asking} onPress={() => void later()} testID="notices-later" />
          </>
        )
      }
    >
      <Text variant="footnote" tone="mutedForeground">
        {t("app.notices.privacy")}
      </Text>
    </EntryFrame>
  );
}

function KindTile({ urgent, icon }: { urgent: boolean; icon: IconName }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.tile, { backgroundColor: urgent ? colors.warningBg : colors.secondary }]}>
      <Icon name={icon} size={20} tone={urgent ? "warningText" : "foreground"} />
    </View>
  );
}

/**
 * A notice as the phone would show it: the app, when, who and why — the same
 * minimum the API sends (031 R8.3). It sits on glass, because a notice is the
 * system's surface, not content (design §3.4): Liquid Glass on iOS 26; opaque
 * with «Reducir transparencia» or before iOS 26; a tonal surface on Android,
 * never imitated blur. A picture of a notice, so the screen reader hears it
 * once, as an example.
 */
function ExampleNotice({ t }: { t: T }) {
  const { colors } = useTheme();
  const { reduceTransparency, increaseContrast } = useSystemAppearance();
  const glass = glassAvailable() && !reduceTransparency;
  const title = t("avisos.example.title");
  const body = t("avisos.example.body");
  const surface = glass
    ? increaseContrast
      ? { borderColor: colors.border, borderWidth: 1 }
      : null
    : {
        backgroundColor: colors.card,
        borderColor: Platform.OS === "android" ? colors.borderSoft : colors.border,
        borderWidth: StyleSheet.hairlineWidth * 2,
      };
  return (
    <View accessible accessibilityLabel={t("avisos.example.a11y", { title, body })} style={[styles.example, surface]}>
      {glass ? <GlassView glassEffectStyle="regular" style={[StyleSheet.absoluteFill, styles.exampleGlass]} /> : null}
      <View style={[styles.appIcon, { backgroundColor: colors.brandGround }]}>
        <Icon name={icons.hand} size={20} tone="highlight" />
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
        <Text variant="callout" tone="mutedForeground" numberOfLines={1}>
          {body}
        </Text>
      </View>
    </View>
  );
}

const EXAMPLE_RADIUS = RADII.xl + 2;

const styles = StyleSheet.create({
  lead: { gap: 16, paddingTop: 8 },
  kinds: { gap: 4 },
  kind: { flexDirection: "row", gap: 12, alignItems: "flex-start", paddingVertical: 8 },
  tile: { width: 36, height: 36, borderRadius: RADII.md - 2, alignItems: "center", justifyContent: "center", borderCurve: "continuous" },
  text: { flex: 1, minWidth: 0, gap: 2 },
  example: {
    flexDirection: "row",
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: EXAMPLE_RADIUS,
    borderCurve: "continuous",
    overflow: "hidden",
    marginVertical: 6,
  },
  exampleGlass: { borderRadius: EXAMPLE_RADIUS },
  appIcon: { width: 38, height: 38, borderRadius: RADII.md - 2, alignItems: "center", justifyContent: "center", borderCurve: "continuous" },
  exampleHead: { flexDirection: "row", gap: 8, alignItems: "baseline" },
  denied: { flexDirection: "row", alignItems: "flex-start", gap: 10, paddingVertical: 6, paddingHorizontal: 4 },
});
