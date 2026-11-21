import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { useT } from "@/i18n/t";
import { CARD_RADIUS, RADII, useTheme } from "@/theme/theme";
import { SKELETON_DELAY_MS } from "@/ui/states";

/**
 * Inicio loading (spec 069, R3.1): the final layout's own measures — the
 * business line, the 2 × 2 tiles and the list under them — so nothing jumps
 * when the figures arrive. Shown only past 300 ms, like every skeleton.
 */
export function HomeSkeleton() {
  const t = useT();
  const { colors } = useTheme();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setVisible(true), SKELETON_DELAY_MS);
    return () => clearTimeout(id);
  }, []);
  const ghost = { backgroundColor: colors.muted };
  return (
    <View accessible accessibilityRole="progressbar" accessibilityLabel={t("app.loading")} accessibilityState={{ busy: true }} testID="skeleton" style={styles.stack}>
      {visible ? (
        <>
          <View style={[styles.line, ghost]} />
          <View style={styles.grid}>
            {[0, 1].map((r) => (
              <View key={r} style={styles.row}>
                <View style={[styles.tile, ghost]} />
                <View style={[styles.tile, ghost]} />
              </View>
            ))}
          </View>
          <View style={[styles.block, ghost]} />
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 14 },
  line: { width: "60%", height: 14, borderRadius: RADII.sm, marginTop: 4 },
  grid: { gap: 10 },
  row: { flexDirection: "row", gap: 10 },
  tile: { flex: 1, height: 96, borderRadius: CARD_RADIUS },
  block: { height: 120, borderRadius: CARD_RADIUS, marginTop: 2 },
});
