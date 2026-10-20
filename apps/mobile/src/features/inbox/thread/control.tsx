import { StyleSheet, View } from "react-native";

import type { T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import type { ComposerMode } from "../model";

/**
 * The bottom of a conversation nobody here answers yet (R6.1): why it waits,
 * said BEFORE the action, and «Tomar el control» full width under the thumb.
 * When the agent or another person answers, who — and the same action.
 * Resolved: it says so, and «Reabrir».
 */
export function ControlCard({
  mode,
  busy,
  online,
  t,
  onTakeOver,
  onGiveBack,
  onReopen,
}: {
  mode: Exclude<ComposerMode, { kind: "mine" }>;
  busy: boolean;
  online: boolean;
  t: T;
  onTakeOver: () => void;
  onGiveBack: () => void;
  onReopen: () => void;
}) {
  const { colors, radius } = useTheme();
  const off = busy || !online;

  if (mode.kind === "resolved") {
    return (
      <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: radius.md }]}>
        <Text variant="callout" tone="mutedForeground">
          {t("inbox.composer.resolved")}
        </Text>
        <Button label={t("inbox.action.reopen")} variant="secondary" full busy={busy} disabled={!online} onPress={onReopen} />
      </View>
    );
  }

  if (mode.kind === "waiting") {
    return (
      <View
        style={[styles.card, { backgroundColor: colors.warningBg, borderColor: colors.warningSolid, borderRadius: radius.md }]}
        testID="waiting-card"
      >
        <View style={styles.head}>
          <Icon name={icons.hand} size={18} tone="warningText" />
          <Text variant="bodyStrong" style={styles.flex} accessibilityRole="header">
            {t("inbox.composer.waiting.title")}
          </Text>
        </View>
        <Text variant="callout">{mode.reason ?? t("inbox.composer.waiting.noReason")}</Text>
        <Button label={t("inbox.composer.takeover")} full busy={busy} disabled={!online} onPress={onTakeOver} testID="take-over" />
        <Button label={t("inbox.composer.giveBack")} variant="ghost" full disabled={off} onPress={onGiveBack} />
      </View>
    );
  }

  return (
    <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: radius.md }]}>
      <View style={styles.head}>
        <Icon name={icons.bot} size={18} tone="primaryText" />
        <Text variant="callout" tone="mutedForeground" style={styles.flex}>
          {mode.kind === "agent" ? t("inbox.composer.agent") : t("inbox.composer.other", { name: mode.name ?? t("inbox.who.someone") })}
        </Text>
      </View>
      <Button label={t("inbox.composer.takeover")} variant="secondary" full busy={busy} disabled={!online} onPress={onTakeOver} testID="take-over" />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 12, gap: 10, borderWidth: StyleSheet.hairlineWidth * 2 },
  head: { flexDirection: "row", alignItems: "center", gap: 8 },
  flex: { flex: 1, minWidth: 0 },
});
