import type { ReactNode } from "react";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";

import { useTheme } from "@/theme/theme";
import { Card } from "@/ui/card";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * One figure with its meaning: the label, the number, a line that says what it
 * means, and optionally where to act. Tappable as a whole when it leads
 * somewhere — the whole card is the target, never a tiny link.
 */
export function Metric({
  icon,
  label,
  value,
  hint,
  tone,
  children,
  onPress,
  accessibilityHint,
  testID,
}: {
  icon: IconName;
  label: string;
  value: string;
  hint?: string;
  tone?: "danger" | "warning";
  children?: ReactNode;
  onPress?: () => void;
  accessibilityHint?: string;
  testID?: string;
}) {
  const { colors } = useTheme();
  // Two to a row at the system's normal text size; one each as the text grows,
  // before a label has to break mid-word (R14.3).
  const slot = [styles.slot, { flexBasis: SLOT * useWindowDimensions().fontScale }];
  const body = (
    <Card tone={tone} style={styles.card}>
      <View style={styles.head}>
        <View style={[styles.icon, { backgroundColor: colors.positiveBg }]}>
          <Icon name={icon} size={16} tone="primaryText" />
        </View>
        <Text variant="subhead" tone="mutedForeground" style={styles.label}>
          {label}
        </Text>
        {onPress ? <Icon name={icons.chevron} size={12} tone="subtle" /> : null}
      </View>
      <Text variant="figure">{value}</Text>
      {hint ? (
        <Text variant="footnote" tone={tone === "danger" ? "dangerText" : "mutedForeground"}>
          {hint}
        </Text>
      ) : null}
      {children}
    </Card>
  );
  if (!onPress) {
    return (
      <View accessible accessibilityLabel={[label, value, hint].filter(Boolean).join(". ")} style={slot} testID={testID}>
        {body}
      </View>
    );
  }
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[label, value, hint].filter(Boolean).join(". ")}
      accessibilityHint={accessibilityHint}
      onPress={onPress}
      style={({ pressed }) => [...slot, { opacity: pressed ? 0.7 : 1 }]}
      testID={testID}
    >
      {body}
    </Pressable>
  );
}

const SLOT = 160;

const styles = StyleSheet.create({
  slot: { flexGrow: 1, minWidth: 0 },
  card: { flex: 1 },
  head: { flexDirection: "row", alignItems: "center", gap: 8 },
  icon: { width: 28, height: 28, borderRadius: 6, alignItems: "center", justifyContent: "center" },
  label: { flex: 1, minWidth: 0 },
});
