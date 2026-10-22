import { useState, type ReactNode } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, View, type PressableProps } from "react-native";
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";

import { durations } from "@/motion/durations";
import { useSystemAppearance } from "@/theme/system-appearance";
import { TOUCH, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";

import { Icon, type IconName } from "./icon";
import { Text } from "./text";

/**
 * The app's buttons (spec 042, R7.1, R7.2, R4.8, D12). Capsules on every
 * platform, at least 48 × 48 (031 R14.5); the label wraps instead of being
 * cut when the text is large (031 R14.4).
 *
 * The press is the platform's: on iOS the control shrinks to 0,97 inside the
 * fast budget and its background goes to the press tone; on Android it is the
 * ripple. Nothing here ever lowers the opacity — over glass a translucent
 * control stops reading as a control. `disabled` lowers the contrast of the
 * **content** instead (and mutes the fill); `busy` keeps the size and the
 * tones and says so to assistive tech.
 */
type Variant = "primary" | "secondary" | "ghost" | "destructive";

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

/** The iOS press: a scale to 0,97 and back, each inside `durations.fast`; only the tone with «Reducir movimiento». */
function usePress() {
  const { reduceMotion } = useSystemAppearance();
  const scale = useSharedValue(1);
  const [pressed, setPressed] = useState(false);
  const animated = useAnimatedStyle(() => ({ transform: [{ scale: scale.get() }] }));
  const to = (v: number) => {
    if (Platform.OS === "ios" && !reduceMotion) scale.set(withTiming(v, { duration: durations.fast, easing: Easing.out(Easing.quad) }));
  };
  return {
    pressed,
    animated,
    onPressIn: () => {
      setPressed(true);
      to(0.97);
    },
    onPressOut: () => {
      setPressed(false);
      to(1);
    },
  };
}

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
  onPressIn,
  onPressOut,
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
  const press = usePress();
  const off = !!disabled || busy;
  const tones: Record<Variant, { bg: keyof Palette | "transparent"; pressed: keyof Palette; fg: keyof Palette }> = {
    primary: { bg: "primary", pressed: "primaryDeep", fg: "primaryForeground" },
    secondary: { bg: "card", pressed: "muted", fg: "foreground" },
    ghost: { bg: "transparent", pressed: "muted", fg: "primaryText" },
    destructive: { bg: "dangerBg", pressed: "muted", fg: "destructive" },
  };
  const tone = tones[variant];
  const paint = (name: keyof Palette | "transparent") => (name === "transparent" ? "transparent" : colors[name]);
  // Disabled: the content loses contrast and the fill goes quiet; busy keeps the button's own tones.
  const bg = disabled ? (variant === "ghost" ? "transparent" : colors.muted) : press.pressed ? colors[tone.pressed] : paint(tone.bg);
  const fg: keyof Palette = disabled ? "mutedForeground" : tone.fg;
  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: off, busy }}
      disabled={off}
      android_ripple={Platform.OS === "android" ? { color: colors[tone.pressed] } : undefined}
      onPressIn={(e) => {
        press.onPressIn();
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        press.onPressOut();
        onPressOut?.(e);
      }}
      style={[
        styles.base,
        {
          backgroundColor: bg,
          borderRadius: radius.full,
          borderColor: variant === "secondary" && !disabled ? colors.input : "transparent",
          paddingHorizontal: compact ? 12 : 20,
          alignSelf: full ? "stretch" : "flex-start",
        },
        press.animated,
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
    </AnimatedPressable>
  );
}

/** An icon-only button, named for screen readers, with the full touch target: a capsule that tints when pressed. */
export function IconButton({
  icon,
  label,
  tone = "primaryText",
  disabled,
  onPressIn,
  onPressOut,
  ...rest
}: Omit<PressableProps, "children"> & { icon: IconName; label: string; tone?: keyof Palette }) {
  const { colors, radius } = useTheme();
  const press = usePress();
  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      hitSlop={4}
      android_ripple={Platform.OS === "android" ? { color: colors.muted, borderless: true } : undefined}
      onPressIn={(e) => {
        press.onPressIn();
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        press.onPressOut();
        onPressOut?.(e);
      }}
      style={[styles.icon, { borderRadius: radius.full, backgroundColor: press.pressed ? colors.muted : "transparent" }, press.animated]}
      {...rest}
    >
      <Icon name={icon} size={22} tone={disabled ? "mutedForeground" : tone} />
    </AnimatedPressable>
  );
}

const styles = StyleSheet.create({
  base: { minHeight: TOUCH, minWidth: TOUCH, justifyContent: "center", borderWidth: StyleSheet.hairlineWidth * 2, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 10, flexWrap: "wrap" },
  label: { textAlign: "center", flexShrink: 1 },
  icon: { minWidth: TOUCH, minHeight: TOUCH, alignItems: "center", justifyContent: "center", overflow: "hidden" },
});
