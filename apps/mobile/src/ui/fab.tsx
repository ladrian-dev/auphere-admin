import { GlassView } from "expo-glass-effect";
import { Platform, Pressable, StyleSheet, View } from "react-native";

import { glassAvailable } from "@/theme/glass";
import { useSystemAppearance } from "@/theme/system-appearance";
import { useTheme } from "@/theme/theme";

import { Icon, type IconName } from "./icon";
import { Text } from "./text";

/**
 * A floating button (spec 044, research D6): a control over the content, so on
 * iOS 26 it is the system's interactive glass with the icon in the one accent
 * colour; before 26, or with «Reducir transparencia», an opaque circle. On
 * Android it is Material 3's: a 56 dp square of radius 16, `extended` with its
 * words, `small` (40 dp) when it is the second one stacked above. It never sits
 * on another glass surface and is never translucent by opacity.
 */
export function Fab({
  icon,
  label,
  onPress,
  extended = false,
  small = false,
  testID,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  extended?: boolean;
  small?: boolean;
  testID?: string;
}) {
  const { colors } = useTheme();
  const { reduceTransparency } = useSystemAppearance();
  const glass = glassAvailable() && !reduceTransparency;
  const size = small ? 40 : 56;
  const radius = Platform.OS === "android" ? (small ? 12 : 16) : size / 2;
  const showLabel = extended && Platform.OS === "android";

  if (glass) {
    return (
      <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} testID={testID} hitSlop={4}>
        <GlassView isInteractive style={[styles.center, { width: size, height: size, borderRadius: radius }]}>
          <Icon name={icon} size={small ? 18 : 24} tone="primaryText" />
        </GlassView>
      </Pressable>
    );
  }
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      testID={testID}
      hitSlop={4}
      android_ripple={{ color: colors.primaryDeep, foreground: true }}
      style={({ pressed }) => [
        styles.center,
        styles.shadow,
        {
          minWidth: size,
          height: size,
          borderRadius: radius,
          backgroundColor: pressed && Platform.OS === "ios" ? colors.primaryDeep : colors.primary,
          paddingHorizontal: showLabel ? 16 : 0,
          shadowColor: colors.foreground,
        },
      ]}
    >
      <View style={styles.row}>
        <Icon name={icon} size={small ? 18 : 24} tone="primaryForeground" />
        {showLabel ? (
          <Text variant="bodyStrong" tone="primaryForeground" maxFontSizeMultiplier={1.3}>
            {label}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: "center", justifyContent: "center", overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  shadow: { elevation: 3, shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.18, shadowRadius: 6 },
});
