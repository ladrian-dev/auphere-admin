import { GlassView } from "expo-glass-effect";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ScrollView, StyleSheet, View, useWindowDimensions, type LayoutChangeEvent, type StyleProp, type ViewStyle } from "react-native";
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming, type SharedValue } from "react-native-reanimated";

import { durations } from "@/motion/durations";
import { glassAvailable } from "@/theme/glass";
import { useSystemAppearance } from "@/theme/system-appearance";
import { CARD_RADIUS, useTheme } from "@/theme/theme";

/** The breathing room the list keeps between its last row and the surface. */
export const FOOT_GAP = 8;
/** The most of the window the surface may take; the thread keeps the rest, scrollable (spec 042, R4.7). */
export const FOOT_MAX_SHARE = 0.6;

/**
 * One surface for the foot of a conversation (spec 042, R2.1, R2.5, R3.1,
 * R4.2, R4.3, D3). Two presentations, one code:
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
 *
 * **It animates its own height.** The content is measured and the container's
 * height follows it with `withTiming` (spike S2, check 1): a layout
 * transition on a wrapper only moves the wrapper and the glass snaps. The
 * first measure sets the height outright; with «Reducir movimiento», every
 * one does. The screen can hand in a shared value for the **clearance** — the
 * space the surface takes from the bottom edge: content, border, margin and
 * a gap — and use it as the list's padding, so the last row always clears
 * the surface and moves with it.
 *
 * **It never takes the whole screen.** With the text at its largest the
 * waiting panel can outgrow the window; the surface stops at
 * `FOOT_MAX_SHARE` of it and its content scrolls inside, so the thread keeps
 * the rest and any message can still be reached (R4.7).
 */
export function FloatingSurface({
  tone = "neutral",
  radius = CARD_RADIUS,
  bottomInset = 0,
  clearance,
  onClearance,
  style,
  testID,
  onLayout,
  children,
}: {
  tone?: "neutral" | "warning";
  radius?: number;
  /** The safe area under the surface: a margin when it floats, padding inside when it is docked. */
  bottomInset?: number;
  /** Where to write the clearance (content, border, margin and `FOOT_GAP`); the surface animates this very value. */
  clearance?: SharedValue<number>;
  /** The same clearance as a plain number, each time it settles: for a list that keeps its padding in React state. */
  onClearance?: (px: number) => void;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  onLayout?: (e: LayoutChangeEvent) => void;
  children: ReactNode;
}) {
  const { colors } = useTheme();
  const { reduceTransparency, increaseContrast, reduceMotion } = useSystemAppearance();
  const glass = glassAvailable() && !reduceTransparency;
  const own = useSharedValue(0);
  const target = clearance ?? own;
  /** The content's last measured height (capped), so the clearance can be redone when only the frame around it changes. */
  const content = useRef<number | null>(null);
  const cap = Math.round(useWindowDimensions().height * FOOT_MAX_SHARE);
  const [overflows, setOverflows] = useState(false);
  const border = tone === "warning" ? colors.warningSolid : colors.border;
  const defined = increaseContrast || tone === "warning" ? { borderWidth: 1, borderColor: border } : null;
  const margin = glass ? bottomInset + 8 : 0;
  // What the clearance holds besides the content: the border (the height includes it), the floating margin, the gap.
  const extra = (defined ? 2 : 0) + margin + FOOT_GAP;
  // Shared values are written through `set`, never assigned: the one the screen hands in is a prop.
  const animated = useAnimatedStyle(() => {
    const h = target.get() - FOOT_GAP - margin;
    return h > 0 ? { height: h } : {};
  });
  const settle = (height: number, animate: boolean) => {
    const next = height + extra;
    target.set(animate ? withTiming(next, { duration: durations.state, easing: Easing.out(Easing.cubic) }) : next);
    onClearance?.(next);
  };
  const measure = (e: LayoutChangeEvent) => {
    const first = content.current === null;
    const height = e.nativeEvent.layout.height;
    setOverflows(height > cap);
    content.current = Math.min(height, cap);
    settle(content.current, !first && !reduceMotion);
  };
  // The frame can change with the content still: a border with «Aumentar contraste», the margin when the material swaps.
  useEffect(() => {
    if (content.current === null) return;
    target.set(content.current + extra);
    onClearance?.(content.current + extra);
  }, [extra, target, onClearance]);

  return (
    <Animated.View
      testID={testID}
      onLayout={onLayout}
      style={[
        glass
          ? [styles.floating, { borderRadius: radius, borderCurve: "continuous" as const, marginBottom: bottomInset + 8 }]
          : [styles.docked, { backgroundColor: colors.card, borderTopColor: border }],
        defined,
        animated,
        style,
      ]}
    >
      {glass ? <GlassView glassEffectStyle="regular" style={StyleSheet.absoluteFill} testID="glass-view" /> : null}
      <ScrollView
        testID={testID ? `${testID}-scroll` : undefined}
        scrollEnabled={overflows}
        showsVerticalScrollIndicator={overflows}
        bounces={false}
        keyboardShouldPersistTaps="handled"
      >
        <View testID={testID ? `${testID}-content` : undefined} onLayout={measure} style={glass ? null : { paddingBottom: Math.max(bottomInset, 8) }}>
          {children}
        </View>
      </ScrollView>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  floating: { marginHorizontal: 12, overflow: "hidden" },
  docked: { borderTopWidth: StyleSheet.hairlineWidth, overflow: "hidden" },
});
