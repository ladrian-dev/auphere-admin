import { StyleSheet, View } from "react-native";

import { useTheme } from "@/theme/theme";
import { Text } from "@/ui/text";

/**
 * Consumo's spend bars (spec 069, R18.1; design §9.2), drawn with plain views
 * (no chart library on the phone). One bar per day for 7 and 30 days, one per
 * week for 90; a zero is a low bar in the sunken tone, never a gap; three
 * dates on the axis — the start, the middle and today — instead of a label
 * under every bar. For a screen reader the chart is one element whose label
 * reads every bar and its amount: the shape is for the eye, the numbers are
 * for everyone (WCAG 1.1.1).
 */
export type Bar = { value: number; label: string };

const HEIGHT = 132;
/** The design's gaps between bars: wide for a week of days, tight for a month, in between for 13 weeks. */
const GAP: Record<"week" | "month" | "quarter", number> = { week: 14, month: 3, quarter: 8 };

export function SpendBars({
  bars,
  axis,
  summary,
  density,
}: {
  bars: Bar[];
  /** The three dates under the chart: first bar, middle bar, today. */
  axis: [string, string, string];
  /** Spoken instead of the drawing, e.g. «Gasto por día: 2 oct: 1,62 US$, …». */
  summary: string;
  density: keyof typeof GAP;
}) {
  const { colors, radius } = useTheme();
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={summary} style={styles.wrap} testID="spend-chart">
      <View style={[styles.bars, { gap: GAP[density], borderBottomColor: colors.border }]}>
        {bars.map((b, i) => (
          <View
            key={i}
            style={{
              flex: 1,
              minWidth: 2,
              height: b.value > 0 ? Math.max(3, (b.value / max) * (HEIGHT - 4)) : 3,
              backgroundColor: b.value > 0 ? colors.primary : colors.muted,
              // The scale's smallest corner on top, square on the axis: a thin bar of 30 days never turns into a pill.
              borderTopLeftRadius: radius.sm,
              borderTopRightRadius: radius.sm,
            }}
          />
        ))}
      </View>
      <View style={styles.axis} testID="chart-axis">
        {axis.map((label, i) => (
          <Text key={i} variant="caption" tone="mutedForeground" style={styles.tick} numberOfLines={1} maxFontSizeMultiplier={1.6}>
            {label}
          </Text>
        ))}
      </View>
    </View>
  );
}

/**
 * 90 days as 13 weeks (design §9.2): groups of 7 counted back from today, so
 * the last week ends today and the first one holds what is left.
 */
export function weekly(days: readonly string[], cents: readonly number[]): { from: string; to: string; cents: number }[] {
  const out: { from: string; to: string; cents: number }[] = [];
  for (let end = days.length; end > 0; end -= 7) {
    const start = Math.max(0, end - 7);
    let sum = 0;
    for (let i = start; i < end; i++) sum += cents[i] ?? 0;
    out.unshift({ from: days[start] ?? "", to: days[end - 1] ?? "", cents: sum });
  }
  return out;
}

const styles = StyleSheet.create({
  wrap: { gap: 6, marginTop: 6 },
  bars: { flexDirection: "row", alignItems: "flex-end", height: HEIGHT, borderBottomWidth: StyleSheet.hairlineWidth, paddingBottom: 1, overflow: "hidden" },
  axis: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  tick: { fontVariant: ["tabular-nums"] },
});
