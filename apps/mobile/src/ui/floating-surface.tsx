import { GlassView, isLiquidGlassAvailable } from "expo-glass-effect";
import type { ReactNode } from "react";
import { Platform, StyleSheet, View, type LayoutChangeEvent, type StyleProp, type ViewStyle } from "react-native";

import { useSystemAppearance } from "@/theme/system-appearance";
import { CARD_RADIUS, useTheme } from "@/theme/theme";

/**
 * One surface for the foot of a conversation (spec 042, R2.1, R3.1, R4.2,
 * R4.3, D3). Two presentations, one code:
 *
 * - **Glass, floating** — iOS 26 with Liquid Glass and «Reducir transparencia»
 *   off: a `GlassView` behind the content, side margins, a radius, no border.
 * - **Opaque, docked** — anywhere else, or when the person asked for less
 *   transparency: full width, no radius, a hairline on top. Over the list with
 *   its padding it is exactly the foot of the 031.
 *
 * The material is a layer *behind* a stable container, so changing it with
 * the surface mounted never remounts the children (the composer keeps its
 * text). Nothing here ever sets `opacity`: at a low combined alpha the glass
 * does not render at all. With «Aumentar contraste» the surface gets a
 * defined border all round.
 */
export function FloatingSurface({
  tone = "neutral",
  radius = CARD_RADIUS,
  style,
  testID,
  onLayout,
  children,
}: {
  tone?: "neutral" | "warning";
  radius?: number;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  onLayout?: (e: LayoutChangeEvent) => void;
  children: ReactNode;
}) {
  const { colors } = useTheme();
  const { reduceTransparency, increaseContrast } = useSystemAppearance();
  const glass = Platform.OS === "ios" && isLiquidGlassAvailable() && !reduceTransparency;
  const border = tone === "warning" ? colors.warningSolid : colors.border;
  const defined = increaseContrast || tone === "warning" ? { borderWidth: 1, borderColor: border } : null;
  return (
    <View
      testID={testID}
      onLayout={onLayout}
      style={[
        glass
          ? [styles.floating, { borderRadius: radius, borderCurve: "continuous" as const }]
          : [styles.docked, { backgroundColor: colors.card, borderTopColor: border }],
        defined,
        style,
      ]}
    >
      {glass ? <GlassView glassEffectStyle="regular" style={StyleSheet.absoluteFill} testID="glass-view" /> : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  floating: { marginHorizontal: 12, overflow: "hidden" },
  docked: { borderTopWidth: StyleSheet.hairlineWidth },
});
