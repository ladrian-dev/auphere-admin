import { StyleSheet, View } from "react-native";

import { useTheme } from "@/theme/theme";
import { Text } from "@/ui/text";

/**
 * Bars per day, drawn with plain views (no chart library on the phone). For a
 * screen reader the chart is one element whose label reads every day and its
 * value — the shape is for the eye, the numbers are for everyone (WCAG 1.1.1).
 */
export function DayBars({
  values,
  labels,
  summary,
  height = 96,
  every = 1,
}: {
  values: number[];
  labels: string[];
  /** Spoken instead of the drawing, e.g. «2 oct: 5, 3 oct: 21, …». */
  summary: string;
  height?: number;
  /** Show one label every `every` bars, so 30 days still fit. */
  every?: number;
}) {
  const { colors, radius } = useTheme();
  const max = Math.max(1, ...values);
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={summary} style={styles.wrap}>
      <View style={[styles.bars, { height }]}>
        {values.map((v, i) => (
          <View key={i} style={styles.col}>
            <View
              style={{
                height: Math.max(v > 0 ? 3 : 1, (v / max) * height),
                backgroundColor: v > 0 ? colors.primary : colors.border,
                borderTopLeftRadius: radius.sm,
                borderTopRightRadius: radius.sm,
              }}
            />
          </View>
        ))}
      </View>
      <View style={styles.labels}>
        {labels.map((l, i) => (
          <Text key={i} variant="caption" tone="mutedForeground" style={styles.label} numberOfLines={1} maxFontSizeMultiplier={1.3}>
            {i % every === 0 ? l : ""}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: 3 },
  col: { flex: 1, justifyContent: "flex-end" },
  labels: { flexDirection: "row", gap: 3 },
  label: { flex: 1, textAlign: "center", fontSize: 10 },
});
