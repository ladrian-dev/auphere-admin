import { Pressable, StyleSheet } from "react-native";

import { useTheme } from "@/theme/theme";

import { Icon, type IconName } from "./icon";
import { Text } from "./text";

/**
 * A choice chip (spec 031 R5.2; spec 042 R7.1): a capsule, one chosen at a
 * time in its row, a real target with its slop, and it says whether it is
 * chosen. With an icon it is a button that opens something, not a choice.
 * The press is a tint, never a drop in opacity (spec 042, R7.2).
 */
export function Chip({
  label,
  on,
  onPress,
  icon,
  disabled = false,
  accessibilityLabel,
  testID,
}: {
  label: string;
  on: boolean;
  onPress: () => void;
  icon?: IconName;
  disabled?: boolean;
  accessibilityLabel?: string;
  testID?: string;
}) {
  const { colors, radius } = useTheme();
  return (
    <Pressable
      accessibilityRole={icon ? "button" : "radio"}
      accessibilityState={icon ? (disabled ? { disabled } : undefined) : disabled ? { checked: on, disabled } : { checked: on }}
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      // Only when it is: Pressable spells out the whole state otherwise.
      disabled={disabled || undefined}
      hitSlop={{ top: 6, bottom: 6 }}
      android_ripple={{ color: on ? colors.primaryDeep : colors.muted }}
      testID={testID}
      style={({ pressed }) => [
        styles.chip,
        {
          borderRadius: radius.full,
          backgroundColor: disabled ? colors.muted : on ? (pressed ? colors.primaryDeep : colors.primary) : pressed ? colors.muted : colors.card,
          borderColor: disabled ? colors.muted : on ? (pressed ? colors.primaryDeep : colors.primary) : colors.border,
        },
      ]}
    >
      {icon ? <Icon name={icon} size={14} tone="foreground" /> : null}
      <Text variant="subhead" tone={disabled ? "mutedForeground" : on ? "primaryForeground" : "foreground"}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: { minHeight: 36, paddingHorizontal: 14, borderWidth: 1, flexDirection: "row", alignItems: "center", gap: 6 },
});
