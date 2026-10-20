import type { ReactNode } from "react";
import { ActivityIndicator, Pressable, StyleSheet, View, type PressableProps } from "react-native";

import { TOUCH, useTheme } from "@/theme/theme";

import { Icon, type IconName } from "./icon";
import { Text } from "./text";

/**
 * The app's buttons. At least 48 × 48 (R14.5); the label wraps instead of
 * being cut when the text is large (R14.4). `busy` keeps the size and says so
 * to assistive tech.
 */
type Variant = "primary" | "secondary" | "ghost" | "destructive";

export function Button({
  label,
  variant = "primary",
  icon,
  leading,
  busy = false,
  disabled,
  full = false,
  compact = false,
  accessibilityLabel,
  ...rest
}: Omit<PressableProps, "children"> & {
  label: string;
  variant?: Variant;
  icon?: IconName;
  /** Something that is not one of the app's icons, before the label (a brand mark). */
  leading?: ReactNode;
  busy?: boolean;
  full?: boolean;
  /** Same 48 pt target, less padding: for a row of actions. */
  compact?: boolean;
}) {
  const { colors, radius } = useTheme();
  const off = disabled || busy;
  const bg =
    variant === "primary"
      ? colors.primary
      : variant === "destructive"
        ? colors.dangerBg
        : variant === "secondary"
          ? colors.card
          : "transparent";
  const fg =
    variant === "primary"
      ? "primaryForeground"
      : variant === "destructive"
        ? "destructive"
        : variant === "secondary"
          ? "foreground"
          : "primaryText";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !!off, busy }}
      disabled={off}
      style={({ pressed }) => [
        styles.base,
        {
          backgroundColor: bg,
          borderRadius: radius.md,
          borderColor: variant === "secondary" ? colors.input : "transparent",
          paddingHorizontal: compact ? 12 : 20,
          opacity: off ? 0.5 : pressed ? 0.75 : 1,
          alignSelf: full ? "stretch" : "flex-start",
        },
      ]}
      {...rest}
    >
      <View style={styles.row}>
        {busy ? (
          <ActivityIndicator color={colors[fg]} />
        ) : icon ? (
          <Icon name={icon} size={18} tone={fg} />
        ) : (
          (leading ?? null)
        )}
        <Text variant="bodyStrong" tone={fg} style={styles.label}>
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

/** An icon-only button, named for screen readers, with the full touch target. */
export function IconButton({
  icon,
  label,
  tone = "primaryText",
  ...rest
}: Omit<PressableProps, "children"> & { icon: IconName; label: string; tone?: Parameters<typeof Icon>[0]["tone"] }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={4}
      style={({ pressed }) => [styles.icon, { opacity: pressed ? 0.6 : 1 }]}
      {...rest}
    >
      <Icon name={icon} size={22} tone={tone} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { minHeight: TOUCH, minWidth: TOUCH, justifyContent: "center", borderWidth: StyleSheet.hairlineWidth * 2 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 10, flexWrap: "wrap" },
  label: { textAlign: "center", flexShrink: 1 },
  icon: { minWidth: TOUCH, minHeight: TOUCH, alignItems: "center", justifyContent: "center" },
});
