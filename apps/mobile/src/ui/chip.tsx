import { Pressable, StyleSheet } from "react-native";

import { haptics } from "@/motion/haptics";
import { DrawCheck } from "@/motion/micro";
import { useTheme } from "@/theme/theme";

import { Icon, type IconName } from "./icon";
import { Text } from "./text";

/**
 * A choice chip (spec 031 R5.2; spec 042 R7.1): a capsule, one chosen at a
 * time in its row, a real target with its slop, and it says whether it is
 * chosen. With an icon it is a button that opens something, not a choice.
 * The press is a tint, never a drop in opacity (spec 042, R7.2).
 *
 * Spec 069 (R1.2, micro 2): what is chosen is ink with a check that draws
 * itself — tint and check, never colour alone — and the choice ticks the
 * selection haptic. A count (the Bandeja's «Todas 13») goes after the label.
 */
export function Chip({
  label,
  on,
  onPress,
  icon,
  disabled = false,
  accessibilityLabel,
  testID,
  count,
}: {
  label: string;
  on: boolean;
  onPress: () => void;
  icon?: IconName;
  disabled?: boolean;
  accessibilityLabel?: string;
  testID?: string;
  count?: number;
}) {
  const { colors, radius } = useTheme();
  const chosen = on && !icon;
  return (
    <Pressable
      accessibilityRole={icon ? "button" : "radio"}
      accessibilityState={icon ? (disabled ? { disabled } : undefined) : disabled ? { checked: on, disabled } : { checked: on }}
      accessibilityLabel={accessibilityLabel}
      onPress={() => {
        if (!icon && !on) haptics.select();
        onPress();
      }}
      // Only when it is: Pressable spells out the whole state otherwise.
      disabled={disabled || undefined}
      hitSlop={{ top: 6, bottom: 6 }}
      android_ripple={{ color: chosen ? colors.primaryDeep : colors.muted }}
      testID={testID}
      style={({ pressed }) => [
        styles.chip,
        chosen ? styles.chosen : null,
        {
          borderRadius: radius.full,
          backgroundColor: disabled ? colors.muted : chosen ? colors.selection : pressed ? colors.muted : colors.card,
          borderColor: disabled ? colors.muted : chosen ? colors.selection : colors.controlBorder,
          transform: [{ scale: pressed ? 0.96 : 1 }],
        },
      ]}
    >
      {icon ? <Icon name={icon} size={14} tone="foreground" /> : null}
      {chosen ? <DrawCheck size={14} color={colors.onSelection} /> : null}
      <Text variant="subhead" tone={disabled ? "mutedForeground" : chosen ? "onSelection" : "foreground"}>
        {label}
      </Text>
      {count !== undefined ? (
        <Text variant="subhead" tone={chosen ? "onSelection" : "mutedForeground"} style={styles.count}>
          {count}
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: { minHeight: 36, paddingHorizontal: 14, borderWidth: 1, flexDirection: "row", alignItems: "center", gap: 6 },
  chosen: { paddingLeft: 10 },
  count: { fontVariant: ["tabular-nums"] },
});
