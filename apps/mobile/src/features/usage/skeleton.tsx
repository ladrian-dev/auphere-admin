import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { useT } from "@/i18n/t";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { SKELETON_DELAY_MS } from "@/ui/states";

/**
 * Consumo loading (spec 069, R3.1; design §9.1): the balance card, the two
 * rows of the month and the chart card, at their own heights, so nothing jumps
 * when the figures arrive. Shown only past 300 ms, like every skeleton.
 */
export function UsageSkeleton() {
  const t = useT();
  const { colors } = useTheme();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setVisible(true), SKELETON_DELAY_MS);
    return () => clearTimeout(id);
  }, []);
  return (
    <View accessible accessibilityRole="progressbar" accessibilityLabel={t("app.loading")} accessibilityState={{ busy: true }} testID="skeleton" style={styles.stack}>
      {visible ? [150, 120, 260].map((h) => <View key={h} style={[styles.block, { height: h, backgroundColor: colors.muted }]} />) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  block: { borderRadius: CARD_RADIUS },
});
