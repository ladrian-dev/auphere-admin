import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { SKELETON_DELAY_MS } from "@/ui/states";

/**
 * The list while it loads (spec 069, R3.1, micro 5): rows of the final size —
 * the 44 pt avatar, the name and the line — in the same card the rows sit in,
 * so nothing moves when they arrive (the design's own skeleton did not match,
 * §13.10). Shown only past 300 ms: a fast answer never flashes it.
 */
export function InboxSkeleton({ rows = 5, label }: { rows?: number; label: string }) {
  const { colors } = useTheme();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setVisible(true), SKELETON_DELAY_MS);
    return () => clearTimeout(id);
  }, []);
  return (
    <View accessible accessibilityRole="progressbar" accessibilityLabel={label} accessibilityState={{ busy: true }} testID="inbox-skeleton" style={styles.wrap}>
      {visible ? (
        <View style={[styles.card, { backgroundColor: colors.card, borderRadius: CARD_RADIUS }]}>
          {Array.from({ length: rows }, (_, i) => (
            <View key={i} style={styles.row} testID="skeleton-row">
              <View style={[styles.avatar, { backgroundColor: colors.muted }]} />
              <View style={styles.lines}>
                <View style={[styles.bar, { backgroundColor: colors.muted, width: `${58 - (i % 2) * 12}%` }]} />
                <View style={[styles.bar, styles.thin, { backgroundColor: colors.muted, width: `${66 + (i % 2) * 12}%` }]} />
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingHorizontal: 16, paddingTop: 8 },
  card: { overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingLeft: 12, paddingRight: 14, paddingVertical: 10, minHeight: 64 },
  avatar: { width: 44, height: 44, borderRadius: 22 },
  lines: { flex: 1, gap: 8 },
  bar: { height: 13, borderRadius: 6 },
  thin: { height: 11 },
});
