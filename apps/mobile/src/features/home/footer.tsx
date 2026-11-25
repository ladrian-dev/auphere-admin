import { StyleSheet, View } from "react-native";
import Animated, { FadeOut, FadeOutDown, ReduceMotion } from "react-native-reanimated";

import type { Conversation } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { CalmCheck, easeOut } from "@/motion/micro";
import { haptics } from "@/motion/haptics";
import { useSystemAppearance } from "@/theme/system-appearance";
import { RADII, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { agoText, reasonText, waitingReasonText } from "../inbox/model";
import { callName } from "./model";

/**
 * The bottom of Inicio, in the thumb's reach (spec 069, R8.4, R8.5): whoever
 * waits for a person — a white card, amber only in its label and its icon
 * tile (owner, 18 Nov) — with how long, why, «+N más» and «Atender a …»; or,
 * once nobody waits any more, the calm card (micro 8).
 */
export function WaitingCard({
  c,
  count,
  firstId,
  now,
  t,
  n,
  onAttend,
}: {
  /** The first conversation waiting, when the list has it; without it the card says the count. */
  c: Conversation | null;
  /** `home.waiting.count`: the same number as the tab's badge. */
  count: number;
  firstId: string | null;
  now: Date;
  t: T;
  n: (v: number) => string;
  onAttend: (id: string | null) => void;
}) {
  const { colors } = useTheme();
  const since = c?.waiting?.since ?? null;
  const base = since ? t("v13.home.wait.since", { time: agoText(since, now.getTime(), t) }) : t("v13.home.wait.group");
  const kicker = count > 1 ? t("v13.home.wait.more", { text: base, n: n(count - 1) }) : base;
  // Spec 056 (7.1): the agent's reason in words, from its sentence or its code — never a code.
  const reason = c ? (c.waiting?.reason ? reasonText(c.waiting.reason, t) : (waitingReasonText(c.waiting_reason, t) ?? reasonText(null, t))) : null;
  const attend = () => {
    haptics.light();
    onAttend(c?.id ?? firstId);
  };
  return (
    <View
      role="group"
      accessibilityLabel={t("v13.home.wait.group")}
      testID="home-waiting"
      style={[styles.wait, { backgroundColor: colors.card, borderColor: colors.border }]}
    >
      <View style={styles.top}>
        <View style={[styles.tile, { backgroundColor: colors.warningBg }]}>
          <Icon name={icons.hand} size={20} tone="warningText" />
        </View>
        <View style={styles.flex}>
          <Text variant="subhead" tone="warningText">
            {kicker}
          </Text>
          <Text variant="name">{c ? c.contact.name : count === 1 ? t("lite.attention.waiting.one") : t("lite.attention.waiting", { count: n(count) })}</Text>
          {reason ? (
            <Text variant="callout" tone="foreground">
              {reason}
            </Text>
          ) : null}
        </View>
      </View>
      <Button
        label={c ? t("v13.home.wait.attend", { name: callName(c.contact.name) }) : t("lite.attention.attend")}
        icon={icons.hand}
        full
        onPress={attend}
      />
    </View>
  );
}

/** Micro 8: «Todo en orden», with the circle and its check drawing once. Its 3,2 s are the screen's, not here. */
export function CalmCard({ body, t }: { body: string; t: T }) {
  const { colors } = useTheme();
  const { reduceMotion } = useSystemAppearance();
  // It leaves sinking 8 pt and fading (240 ms); with «Reducir movimiento», a fade only (R2.5).
  const exiting = reduceMotion
    ? FadeOut.duration(160).reduceMotion(ReduceMotion.Never)
    : FadeOutDown.duration(240).easing(easeOut()).withInitialValues({ transform: [{ translateY: 0 }] }).reduceMotion(ReduceMotion.Never);
  return (
    <Animated.View exiting={exiting} testID="home-calm">
      <Card>
        <View style={styles.calm} accessible accessibilityRole="text" accessibilityLiveRegion="polite" accessibilityLabel={`${t("v13.home.calm.title")}. ${body}`}>
          <CalmCheck size={44} fill={colors.highlight} ink={colors.onHighlight} />
          <View style={styles.flex}>
            <Text variant="headline">{t("v13.home.calm.title")}</Text>
            <Text variant="footnote" tone="mutedForeground">
              {body}
            </Text>
          </View>
        </View>
      </Card>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wait: { borderRadius: RADII.xl, padding: 14, gap: 12, borderWidth: StyleSheet.hairlineWidth * 2 },
  top: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  tile: { width: 36, height: 36, borderRadius: RADII.sm, alignItems: "center", justifyContent: "center" },
  flex: { flex: 1, minWidth: 0, gap: 2 },
  calm: { flexDirection: "row", alignItems: "center", gap: 14 },
});
